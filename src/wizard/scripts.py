"""Shell scripts present in the pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urlparse

URL = ParseResult


@dataclass
class Parameter:
    """Represents a configuration parameter (such as a file path)."""

    """The name of the parameter (to put into the config file)."""
    name: str

    """The type expected for the parameter."""
    parameter_type: type

    """The default value used for the parameter."""
    default: Any


@dataclass
class Dependency:
    """Represents a script dependency (required prerequisite files).

    Note that this does not include files from previous steps in a pipeline. It
    purely accounts for external files such as refrence fastas.

    """

    """The name of the dependency."""
    name: str

    """An explanation of what the dependency is for."""
    description: str

    """Where to retrieve the file from (or how to make it)."""
    url: URL | str


@dataclass
class Script:
    """Represents a script with associated information."""

    """Path should be relative to the scripts directory."""
    path: str

    """What the script attempts to do."""
    purpose: str

    """Configuration parameters needed."""
    parameters: list[Parameter]

    """File dependencies (for example, a reference genome)."""
    dependencies: list[Dependency]


## Shared dependencies ##
GENOME_FASTA = Dependency(
    "genomeFASTA",
    "The reference genome fasta for flair",
    urlparse(
        "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_44/GRCh38.primary_assembly.genome.fa.gz"
    ),
)
GENOME_GTF = Dependency(
    "genomeGTF",
    "The reference genome GTF for flair",
    urlparse(
        "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_44/gencode.v44.primary_assembly.annotation.gff3.gz"
    ),
)
RRNA_REFERENCE = Dependency(
    "rrna",
    "The rRNA reference for sortmerna.",
    urlparse(
        "https://github.com/sortmerna/sortmerna/releases/download/v4.3.7/smr_v4.3_default_db.fasta.gz"
    ),
)
OUT_DIRECTORY = Parameter("outdir", Path, Path("."))
KEEP_TEMP = Parameter("keep_temp_files", bool, False)

PIPELINE_SCRIPTS = [
    Script(
        "00_splitRawFile.sh",
        "Split multiplexed fastq file into separate files, for parallelised demultiplexing.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "00_zipping.sh",
        "Zip the multiplexed fastq file to save on space.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "02_runCutadapt.sh",
        "Demultiplex the fastq files.",
        [Parameter("minOverlap", int, 30)],
        [],
    ),
    Script(
        "03_mergeCutadapt.sh",
        "Merge demultiplexed files by barcode (required due to splitting of multiplexed fastq)",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "04_runQC.sh",
        "Run fastqc on each demultiplexed fastq file",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "05_alignONT.sh",
        "Use minimap2 to align reads to bam files (+index+sort).",
        [OUT_DIRECTORY, KEEP_TEMP],
        [
            Dependency(
                "refMMI",
                "Reference genome mmi file",
                "Build this index using minimap2 and a genome fasta",
            )
        ],
    ),
    Script(
        "06_mergeBams.sh",
        "Merge together bam files for bambu.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "07_bambu.sh",
        "Run bambu for transcript quantification.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "07_flair.sh",
        "Run flair to identify & quantify full-length transcript isoforms (filtering out isoforms whose splice sites aren't supported by the annotation)",
        [OUT_DIRECTORY, KEEP_TEMP],
        [GENOME_FASTA, GENOME_GTF],
    ),
    Script(
        "08_sqanti3.sh",
        "Run SQANTI3 to employ quality control and filtering of flair isoforms.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [GENOME_FASTA, GENOME_GTF],
    ),
    Script(
        "08_sqanti3Mapping.sh",
        "Run SQANTI3 to employ quality control and filtering of flair isoforms (also completes mapping with minimap2).",
        [OUT_DIRECTORY, KEEP_TEMP],
        [GENOME_FASTA, GENOME_GTF],
    ),
    Script(
        "00_fastQCraw.sh",
        "Run fastqc on each short read fastq file.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "00_mergeFastq.sh",
        "Merge fastq files by read mate.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "00_rsem_indexing.sh",
        "Prepare transcript references for RSEM.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [GENOME_FASTA, GENOME_GTF],
    ),
    Script(
        "00_sortmerna_indexing.sh",
        "Prepare rRNA index from rRNA fasta for SORTMERNA.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [RRNA_REFERENCE],
    ),
    Script(
        "00_star_indexing.sh",
        "Prepare genome and transcriptome references for STAR.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [GENOME_FASTA, GENOME_GTF],
    ),
    Script(
        "01_sortmerna.sh",
        "Match reads to rRNA sequences to remove rRNA contamination.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [RRNA_REFERENCE],
    ),
    Script(
        "02_star.sh",
        "Align reads to the genome and transcriptome.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "03_rsem.sh",
        "Quantification of transcript expression.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "03_sortIndexBam.sh",
        "Sort and index bam files from STAR.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "04_getQCvalues.R",
        "Creates a table of quality control values from SORTMERNA, STAR, and RSEM.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
    Script(
        "05_DESeq2Template.R",
        "Template to show users how to import RSEM results into DESeq2 using tximport.",
        [OUT_DIRECTORY, KEEP_TEMP],
        [],
    ),
]
