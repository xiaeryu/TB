## Copyright (C) 2015 Kiatichai Faksri (kiatichaifaksri@gmail.com).
##
## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License
## as published by the Free Software Foundation; either version 3
## of the License, or (at your option) any later version.

## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.

## You should have received a copy of the GNU General Public License
## along with this program; if not, see
## http://www.opensource.org/licenses/gpl-3.0.html

## --------------------------------
## Please report bugs to:
## kiatichaifaksri@gmail.com


import os
import sys
import re
import gzip
import subprocess
from optparse import OptionParser


## Global variables.
dir = os.path.split(os.path.realpath(__file__))[0] # script directory


######################################################
## Options and arguments
######################################################
usage = "usage: %prog [options] FASTQ_1 FASTQ_2(optional)"
parser = OptionParser(usage=usage, version="%prog 1.0")

# Output arguments
parser.add_option("-O","--outdir",action="store",type="string",dest="outdir",default=".",help="output directory [Default: running directory]")
parser.add_option("-o","--output",action="store",type="string",dest="output",default="RD-Analyzer",help="basename of output files [Default: RD-Analyzer]")

# Personalized parameters
parser.add_option("-p","--personalized",action="store_true",dest="personalized",help="use personalized cut-offs")
parser.add_option("-m","--min",action="store",type="int",dest="min",help="minimum depth as a cut-off, used when '-p' is set")
parser.add_option("-c","--coverage",action="store",type="float",dest="coverage",help="minimum coverage of an RD sequence as a cut-off, used when '-p' is set")

# Debug mode
parser.add_option("-d","--debug",action="store_true",dest="debug",help="enable debug mode, keeping all intermediate files")

# Parse options
(options, args) = parser.parse_args()

outdir = options.outdir
output = options.output
personalized = options.personalized
min = options.min
coverage = options.coverage
debug = options.debug



#########################################################
## Input check
#########################################################

## Check input fastq files
narg = len(args)
if narg == 0:
    print "usage: python " + os.path.realpath(__file__) + " [options] FASTQ_1 FASTQ_2(optional)"
    sys.exit()
elif narg == 1:
    input1 = args[0]    # Input fastq file 1
    if not os.path.isfile(input1):
        print "Invalid FASTQ 1 file!"
        sys.exit()
elif narg == 2:
    input1 = args[0]    # Input fastq file 1
    input2 = args[1]    # Input fastq file 2
    if not os.path.isfile(input1):
        print "Invalid FASTQ_1 file!"
        sys.exit()
    elif not os.path.isfile(input2):
        print "Invalid FASTQ_2 file!"
        sys.exit()

## Check input parameters
if personalized:
    if not min or not coverage:
        print "Please specify '-m' and '-c' when using '-p' for personalized cut-off!"
        sys.exit()

    min = int(min)
    if coverage < 0 or coverage > 1:
        print "Invalid '-c' option! Please specify a number between 0 and 1."
        sys.exit()
else:
    if min or coverage:
        print "'-m' or '-c' only works when '-p' is used for personalized cut-off!"
        sys.exit()

## Check output options
outprefix = outdir+"/"+output
if os.path.isfile(outprefix+'.sam') or os.path.isfile(outprefix+'.bam') or os.path.isfile(outprefix+'.sort.bam') or os.path.isfile(outprefix+'.depth') or os.path.isfile(outprefix+'.result'):
    print "Files exist in the output directory with the output prefix specified, refuse to overwrite..."
    sys.exit()

if not os.path.isdir(outdir):
    subprocess.call(["mkdir", outdir])



############################################################
## Main class
############################################################
class Main:
    def calcThroughput(self, infile):
        '''
        This function calculates the number of bases of a fastq file
        '''
        if infile.endswith(".gz"):
            in_handle = gzip.open(infile, 'rb')
        else:
            in_handle = open(infile)

        total = 0
        count = 0
        for line in in_handle:
            if count % 4 == 1:
                line = line.strip('\n')
                total += len(line)
            count = (count + 1) % 4
        in_handle.close()
        return total

    def recLength(self, inbam):
        '''
        This function extracts the length of the reference sequences from bam file
        '''
        output = {}
        process = subprocess.Popen(["samtools", "view", "-H", inbam], stdout=subprocess.PIPE)
        for line in iter(process.stdout.readline, ''):
            if line.startswith('@SQ'):
                line = line.strip('\n')
                tmp = line.split('\t')
                # @SQ     SN:RD711_2      LN:888
                output[tmp[1].split(':')[1]] = int(tmp[2].split(':')[1])
        process.terminate()
        return output


    def median(self, inarr, totalNum):
        '''
        This function calculates the median of a list
        '''
        tmp = inarr[:]
        if len(tmp) < totalNum:
            for i in range(len(tmp),totalNum):
                tmp.append(0)

        sorts = sorted(tmp)
        l = len(sorts)
        if l % 2 == 0:
            return (int(sorts[l/2]) + int(sorts[l/2-1])) / 2
        return sorts[l / 2]


    def calcStats(self, inarr, cutoff, totalNum):
        '''
        This function returns the [max, min, median, #lager_than_cutoff]
        '''
        if len(inarr) == 0:
            return [0, 0, 0, 0]

        least = int(inarr[0])
        most = int(inarr[0])
        pf = 0

        if len(inarr) < totalNum:
            least = 0

        for item in inarr:
            item = int(item)
            if item < least:
                least = item
            if item > most:
                most = item
            if item > cutoff:
                pf += 1
        return [most, least, self.median(inarr, totalNum), pf]


    def dealDeletion(self, inbam, min):
        '''
        This function pays special attention to the 7bp_pks15.1, which can be a 6bp deletion, 7bp deletion, or intact
        '''
        process = subprocess.Popen(["samtools", "view", inbam, "7bp_pks15.1:1-167"], stdout=subprocess.PIPE)
        deletion = []
        for line in iter(process.stdout.readline, ''):
            tmp = line.split('\t')
            cigar = re.sub(r'^\d+S', '', tmp[5])
            match = re.search(r'^(\d+)M(\d+)D',cigar)
            if match:
                start = int(tmp[3]) + int(match.group(1))
                if start >= 152 and start <= 167:
                    deletion.append(match.group(2))
        process.terminate()

        storage = {}
        if len(deletion) == 0:
            return [storage, 'Complete']

        for item in deletion:
            storage[item] =storage.get(item,0) + 1

        maxKey, maxVal = max(storage.iteritems(), key=lambda x:x[1])
        if maxVal >= min:
            return [storage, maxKey+'D']
        else:
            return [storage, 'Complete']


    def predLineage(self, inDict):
        inLineage = {
            "out1":"M.africanum I - Lineage 5 - (RD9, 711)",
            "out2":"M.africanum II - Lineage 6 - (RD9, 7,8,10, pks15/1:6D, 702)",
            "out3":"M.microti - (RD9, 7,8,10, pks15/1:6D, 1mic)",
            "out4":"M.pinnipedii - (RD9, 7,8,10, pks15/1:6D, 2seal)",
            "out5":"M.caprae - (RD9, 7,8,10, pks15/1:6D, 12bov)",
            "out6":"M.bovis (classical) - (RD9, 7,8,10, pks15/1:6D, 12bov, 4)",
            "out7":"M.bovis BCG (Moreau) - (RD9, 7,8,10, pks15/1:6D, 12bov, 4, 1bcg",
            "out8":"M.bovis BCG (Merieux) - (RD9, 7,8,10, pks15/1:6D, 12bov, 4, 1bcg, 2bcg)",
            "out9":"M.Canettii - (RD12bov, 12can)",
            "out10":"Mtb: Indo-Oceanic - Lineage 1 - (RD239)",
            "out11":"Mtb: East-African-Indian - Lineage 3 - (RD750)",
            "out12":"Mtb: East Asian - Lineage 2.1 - (no RD deletion)",
            "out13":"Mtb: Euro-American - Lineage 4.3.3 - (pks15/1:7D, RD115)",
            "out14":"Mtb: Euro-American - Lineage 4.5 - (pks15/1:7D, RD122)",
            "out15":"Mtb: Euro-American - Lineage 4.3.4 & sublineages - (pks15/1:7D, RD174)",
            "out16":"Mtb: Euro-American - Lineage 4.1.2.1 - (pks15/1:7D, RD182)",
            "out17":"Mtb: Euro-American - Lineage 4.1.1.1 - (pks15/1:7D, RD183)",
            "out18":"Mtb: Euro-American - Lineage 4.1.1.3 - (pks15/1:7D, RD193)",
            "out19":"Mtb: Euro-American - Lineage 4.8 - (pks15/1:7D, RD219)",
            "out20":"Mtb: Euro-American - Lineage 4.6.1 & sublineages - (pks15/1:7D, RD724)",
            "out21":"Mtb: Euro-American - Lineage 4.6.2 & sublineages - (pks15/1:7D, RD726)",
            "out22":"Mtb: Euro-American - Lineage 4.3.2.1 - (pks15/1:7D, RD761)",
            "out23":"Mtb: Euro-American - Lineage 4.2, 4.4, 4.7 H37Rv-like and others - (pks15/1:7D)",
            "out24":"Mtb: East Asian - Lineage 2 - (RD105)",
            "out25":"Mtb: East Asian - Lineage 2.2, 2.2.2 - (RD105,207)",
            "out26":"Mtb: East Asian - Lineage 2.2.1.2 - (RD105,207,181,142",
            "out27":"Mtb: East Asian - Lineage 2.2.1 - (RD105,207,181)",
            "out28":"Mtb: East Asian - Lineage 2.2.1.1 - (RD105,207,181,150)",
        }

        if inDict['RD9_1'] == 'A':
            if inDict['RD711_2'] == 'A':
                return inLineage['out1']
            else:
                if inDict['RD7_9'] == 'A' and inDict['RD8_10'] == 'A' and inDict['RD10_11'] == 'A':
                    if inDict['RD702_3'] == 'A':
                        return inLineage['out2']
                    else:
                        if inDict['RD1mic_6'] == 'A':
                            return inLineage['out3']
                        else:
                            if inDict['RD2seal_7'] == 'A':
                                return inLineage['out4']
                            else:
                                if inDict['RD4_4'] == 'P':
                                    return inLineage['out5']
                                else:
                                    if inDict['RD1bcg_5'] == 'P':
                                        return inLineage['out6']
                                    else:
                                        if inDict['RD2bcg_8'] == 'P':
                                            return inLineage['out7']
                                        else:
                                            return inLineage['out8']
        else:
            if inDict['RD12bovis_12'] == 'A' and inDict['RD12can_13'] == 'A':
                return inLineage['out9']
            else:
                if inDict['RD105_14'] == 'A':
                    if inDict['RD207_20'] == 'P':
                        return inLineage['out24']
                    else:
                        if inDict['RD181_19'] == 'P':
                            return inLineage['out25']
                        else:
                            if inDict['RD142_17'] == 'A':
                                return inLineage['out26']
                            else:
                                if inDict['RD150_18'] == 'P':
                                    return inLineage['out27']
                                else:
                                    return inLineage['out28']
                else:
                    if inDict['RD239_15'] == 'A':
                        return inLineage['out10']
                    else:
                        if inDict['RD750_16'] == 'A':
                            return inLineage['out11']
                        else:
                            if inDict['7bp_pks15.1'] == 'Complete':
                                return inLineage['out12']
                            elif inDict['7bp_pks15.1'] == '7D':
                                if inDict['RD115_21'] == 'A':
                                    return inLineage['out13']
                                else:
                                    if inDict['RD122_22'] == 'A':
                                        return inLineage['out14']
                                    else:
                                        if inDict['RD174_23'] == 'A':
                                            return inLineage['out15']
                                        else:
                                            if inDict['RD182_24'] == 'A':
                                                return inLineage['out16']
                                            else:
                                                if inDict['RD183_25'] == 'A':
                                                    return inLineage['out17']
                                                else:
                                                    if inDict['RD193_26'] == 'A':
                                                        return inLineage['out18']
                                                    else:
                                                        if inDict['RD219_27'] == 'A':
                                                            return inLineage['out19']
                                                        else:
                                                            if inDict['RD724_28'] == 'A':
                                                                return inLineage['out20']
                                                            else:
                                                                if inDict['RD726_29'] == 'A':
                                                                    return inLineage['out21']
                                                                else:
                                                                    if inDict['RD761_30'] == 'A':
                                                                        return inLineage['out22']
                                                                    else:
                                                                        return inLineage['out23']

        return 'Undetermined'



############################################################
## Code starts here
############################################################
if __name__ == "__main__":
    t = Main()

    # Index reference file
    try:
        subprocess.call(["bwa", "index", dir+"/Reference/RDs30.fasta"])
    except OSError:
        print "Please check the installation of BWA."
        raise

    try:
        subprocess.call(["samtools", "faidx", dir+"/Reference/RDs30.fasta"])
    except OSError:
        print "Please check the installation of samtools."
        raise

    # BWA alignment
    if narg == 1:
        os.system("bwa mem -R '@RG\\tID:RD\\tSM:RD\\tLB:RD\\tPL:Illumina' %s %s > %s" % ( dir+"/Reference/RDs30.fasta", input1, outprefix+".sam"))

    if narg == 2:
        os.system("bwa mem -R '@RG\\tID:RD\\tSM:RD\\tLB:RD\\tPL:Illumina' %s %s %s > %s" % ( dir+"/Reference/RDs30.fasta", input1, input2, outprefix+".sam"))

    # Sam to Bam
    os.system("samtools view -bS %s -o %s" % (outprefix+".sam", outprefix+".bam"))

    # Sort Bam file
    os.system("samtools sort %s %s" % (outprefix+".bam", outprefix+".sort"))
    os.system("samtools index %s" % outprefix+".sort.bam")

    # Calculate depth
    os.system("samtools depth %s > %s" % (outprefix+".sort.bam", outprefix+".depth"))

    # Throughput calculation:
    throughput = t.calcThroughput(input1)
    if narg == 2:
        throughput += t.calcThroughput(input2)
    depth = throughput *1.0 / 4500000

    # Cut-off definition if not personalized
    if not personalized:
        min = 0.17 * throughput / 4500000
        coverage = 0.5

    # RDs included in the analysis
    RDs = ["RD9_1","RD711_2","RD702_3","RD4_4","RD1bcg_5","RD1mic_6","RD2seal_7","RD2bcg_8","RD7_9","RD8_10","RD10_11","RD12bovis_12","RD12can_13","RD105_14","RD239_15","RD750_16","RD142_17","RD150_18","RD181_19","RD207_20","RD115_21","RD122_22","RD174_23","RD182_24","RD183_25","RD193_26","RD219_27","RD724_28","RD726_29","RD761_30"]


    # Record length of the reference sequences
    RD_length = t.recLength(outprefix+".sort.bam")

    # Summary of the depth file
    storage = {}
    for RD in RDs:
        storage[RD] = []

    depthH = open(outprefix+".depth")
    for line in depthH:
        line = line.strip('\n')
        tmp = line.split('\t')
        if tmp[0] in storage:
            storage[tmp[0]].append(tmp[2])
    depthH.close()

    # Result matrix
    resultMat = []
    resultDict = {}
    for RD in RDs:
        outStats = t.calcStats(storage[RD], min, RD_length[RD])
        percentage = outStats[3]/1.0/RD_length[RD]
        prediction = 'A'
        if percentage > coverage:
            prediction = 'P'
        resultMat.append([RD, outStats[0], outStats[1], outStats[2], outStats[3], RD_length[RD], "%.2f" % percentage, prediction])
        resultDict[RD] = prediction

    # Dealing with 7bp_pks15.1
    [deletionStat,deletionPred] = t.dealDeletion(outprefix+'.sort.bam', min)
    resultMat.append(["7bp_pks15.1", "--", "--", "--", "--", "--", deletionStat, deletionPred])
    resultDict["7bp_pks15.1"] = deletionPred

    # Lineage prediction
    lineage = t.predLineage(resultDict)

    # Format output file
    outH = open(outprefix+".result", 'w')
    outH.write("# Input: " + input1 + '\n')
    if narg == 2:
        outH.write("# Input: " + input2 + '\n')
    outH.write("# Number of bases in the input file(s): %d\n" % throughput)
    outH.write("# Estimated read depth (#Bases/(4.5Mbp)): %.2f\n" % depth)
    outH.write("# Minimum depth cut-off: %.2f\n" % min)
    outH.write("# Minimum coverage cut-off: " + str(coverage) + '\n')
    outH.write("\n# Predicted lineage: " + lineage + '\n\n')
    outH.write("# RD_name\tMaximum_depth\tMinimum_depth\tMedian_depth\t#pos_pass_cutoff\t#total_pos\t%pos_pass_cutoff\tPrediction\n")

    for i in range(len(resultMat)):
        outH.write(str(resultMat[i][0]))
        for j in range(1, len(resultMat[i])):
             outH.write("\t%s" % str(resultMat[i][j]))
        outH.write('\n')

    # Cleaning up
    if not debug:
        post = ['.sam','.bam','.sort.bam','.sort.bam.bai']
        for i in post:
            os.remove("%s%s" % (outprefix,i))
