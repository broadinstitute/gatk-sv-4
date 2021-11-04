#!/usr/bin/env python
# -*- coding: utf-8 -*-
#

"""
Apply batch effect labels to VCF from Talkowski SV pipeline
"""


import argparse
import sys
import pysam
import csv


def reclassify_record(record, reclass, plus_samples):
    if 'PCRPLUS_ENRICHED' in reclass:
        record.filter.add('PCRPLUS_ENRICHED')
    if 'PCRPLUS_DEPLETED' in reclass:
        if 'PCRPLUS_DEPLETED' not in record.info.keys():
            record.info.keys().append('PCRPLUS_DEPLETED')
        record.info['PCRPLUS_DEPLETED'] = True
    if 'VARIABLE_ACROSS_BATCHES' in reclass:
        record.filter.add('VARIABLE_ACROSS_BATCHES')
    if 'UNSTABLE_AF_PCRPLUS' in reclass:
        if 'UNSTABLE_AF_PCRPLUS' not in record.info.keys():
            record.info.keys().append('UNSTABLE_AF_PCRPLUS')
        record.info['UNSTABLE_AF_PCRPLUS'] = True
    if 'UNSTABLE_AF_PCRMINUS' in reclass:
        record.filter.add('UNSTABLE_AF_PCRMINUS')

    if 'PCRPLUS_ENRICHED' in reclass \
            or 'UNSTABLE_AF_PCRPLUS' in reclass:
        for samp in record.samples:
            if samp not in plus_samples:
                record.samples[samp]['GT'] = (None, None)

    if 'PCRPLUS_DEPLETED' in reclass \
            or 'UNSTABLE_AF_PCRMINUS' in reclass:
        for samp in record.samples:
            if samp in plus_samples:
                record.samples[samp]['GT'] = (None, None)

    return record


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('vcf', help='Input vcf (supports "stdin").')
    parser.add_argument('reclassifications', help='Tab-delimited reclassification' +
                        ' table generated by make_batch_effect_reclassification_table.R.')
    # parser.add_argument('PCRPLUS_samples', help='List of PCRPLUS sample IDs.')
    parser.add_argument('fout', help='Output file (supports "stdout").')
    parser.add_argument('--unstable-af-pcrplus', help='List of variant IDs to ' +
                        'be tagged as unstable AF in PCRPLUS samples.')
    parser.add_argument('--unstable-af-pcrminus', help='List of variant IDs to ' +
                        'be tagged as unstable AF in PCRMINUS samples.')

    args = parser.parse_args()

    # Open connection to input VCF
    if args.vcf in '- stdin'.split():
        vcf = pysam.VariantFile(sys.stdin)
    else:
        vcf = pysam.VariantFile(args.vcf)

    # Add new FILTER lines to VCF header
    NEW_FILTERS = ['##FILTER=<ID=PCRPLUS_ENRICHED,Description="Site enriched for ' +
                   'non-reference genotypes among PCR+ samples. Likely reflects ' +
                   'technical batch effects. All PCR- samples have been assigned ' +
                   'null GTs for these sites.>"',
                   '##FILTER=<ID=VARIABLE_ACROSS_BATCHES,Description="Site appears ' +
                   'at variable frequencies across batches. Likely reflects technical ' +
                   'batch effects.>',
                   '##FILTER=<ID=UNSTABLE_AF_PCRMINUS,Description="Allele frequency ' +
                   'for this variant in PCR- samples is sensitive to choice of GQ ' +
                   'filtering thresholds. All PCR- samples have been assigned null ' +
                   'GTs for these sites.>']

    header = vcf.header
    for filt in NEW_FILTERS:
        header.add_line(filt)

    # Add new INFO lines to VCF header
    NEW_INFOS = ['##INFO=<ID=PCRPLUS_DEPLETED,Number=0,Type=Flag,Description=' +
                 '"Site depleted for non-reference genotypes among PCR+ samples. ' +
                 'Likely reflects technical batch effects. All PCR+ samples have ' +
                 'been assigned null GTs for these sites.">',
                 '##INFO=<ID=UNSTABLE_AF_PCRPLUS,Number=0,Type=Flag,Description=' +
                 '"Allele frequency for this variant in PCR+ samples is sensitive ' +
                 'to choice of GQ filtering thresholds. All PCR+ samples have been ' +
                 ' assigned null GTs for these sites.">']
    for info in NEW_INFOS:
        header.add_line(info)

    # Read reclassification table & add unstable AF files
    reclass_table = {}
    with open(args.reclassifications) as rct:
        reader = csv.reader(rct, delimiter='\t')
        for VID, assignment in reader:
            if VID not in reclass_table.keys():
                reclass_table[VID] = [assignment]
            else:
                reclass_table[VID].append(assignment)
    rct.close()
    if args.unstable_af_pcrplus is not None:
        uaf_plus_vids = [line.rstrip('\n')
                         for line in open(args.unstable_af_pcrplus)]
        assignment = 'UNSTABLE_AF_PCRPLUS'
        for VID in uaf_plus_vids:
            if VID not in reclass_table.keys():
                reclass_table[VID] = [assignment]
            else:
                reclass_table[VID].append(assignment)
    if args.unstable_af_pcrminus is not None:
        uaf_minus_vids = [line.rstrip('\n')
                          for line in open(args.unstable_af_pcrminus)]
        assignment = 'UNSTABLE_AF_PCRMINUS'
        for VID in uaf_minus_vids:
            if VID not in reclass_table.keys():
                reclass_table[VID] = [assignment]
            else:
                reclass_table[VID].append(assignment)

    # Read list of PCR+ samples
    # f_plus_samples = open(args.PCRPLUS_samples, 'r')
    # plus_samples = f_plus_samples.read().splitlines()
    # f_plus_samples.close()
    plus_samples = []

    # Open connection to output VCF
    if args.fout in '- stdout'.split():
        fout = pysam.VariantFile(sys.stdout, 'w', header=vcf.header)
    else:
        fout = pysam.VariantFile(args.fout, 'w', header=vcf.header)

    # Iterate over VCF and process records accordingly
    NULL_GTs = [(0, 0), (None, None), (0, ), (None, ), (None, 2)]
    for record in vcf:
        reclass = reclass_table.get(record.id, None)
        if reclass is None:
            fout.write(record)
        else:
            newrecord = reclassify_record(record, reclass, plus_samples)
            # Only write modified records to file if at least one non-ref allele is retained
            for s in vcf.header.samples:
                if newrecord.samples[s]['GT'] not in NULL_GTs:
                    fout.write(newrecord)
                    break

    fout.close()


if __name__ == '__main__':
    main()
