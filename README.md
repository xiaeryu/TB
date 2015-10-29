TB
===

**Usage:**
```Unix
python2.7 script.py [options] FASTQ_1 FASTQ_2(optional)
```
**Options:**  
#####--version  
  show program's version number and exit  
#####-h, --help
  show this help message and exit  
#####-O OUTDIR, --outdir=OUTDIR  
  output directory [Default: running directory]  
#####-o OUTPUT, --output=OUTPUT  
  basename of output files [Default: RD-analyzer]  
#####-p, --personalized
  use personalized cut-offs  
#####-m MIN, --min=MIN
  minimum depth as a cut-off, used when '-p' is set [Default: 10% of the read depth]  
#####-c COVERAGE, --coverage=COVERAGE  
  minimum coverage of an RD sequence as a cut-off, used when '-p' is set [Default: 80%]  
#####-d, --debug
  enable debug mode, keeping all intermediate files  
