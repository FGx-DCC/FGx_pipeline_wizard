"""Shell scripts present in the pipeline."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import ParseResult

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

    """Where to retrieve the file from."""
    url: URL


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


scripts = [
    Script(
        "00_splitRawFile.sh",
        "Split multiplexed fastq file into separate files, for parallelised demultiplexing.",
        [],
        [],
    ),
    Script(
        "00_zipping.sh",
        "Zip the multiplexed fastq file to save on space.",
        [],
        [],
    ),
    Script(
        "02_runCutadapt.sh",
        "Demultiplex the fastq files.",
        [],
        [],
    ),
    Script(
        "03_mergeCutadapt.sh",
        "Merge demultiplexed files by barcode (required due to splitting of multiplexed fastq)",
        [],
        [],
    ),
    Script(
        "04_runQC.sh",
        "Run fastqc on each demultiplexed fastq file",
        [],
        [],
    ),
    Script(
        "05_alignONT.sh",
        "Use minimap2 to align reads to bam files (+index+sort).",
        [],
        [],
    ),
    Script(
        "06_mergeBams.sh",
        "Merge together bam files for bambu.",
        [],
        [],
    ),
    Script(
        "07_bambu.sh",
        "Run bambu for transcript quantification.",
        [],
        [],
    ),
    Script(
        "07_flair.sh",
        "Run flair to identify & quantify full-length transcript isoforms (filtering out isoforms whose splice sites aren't supported by the annotation)",
        [],
        [],
    ),
    Script(
        "08_sqanti3.sh",
        "Run SQANTI3 to employ quality control and filtering of flair isoforms.",
        [],
        [],
    ),
    Script(
        "00_fastQCraw.sh",
        "Run fastqc on each short read fastq file.",
        [],
        [],
    ),
    Script(
        "00_mergeFastq.sh",
        "Merge fastq files by read mate.",
        [],
        [],
    ),
    Script(
        "00_rsem_indexing.sh",
        "Prepare transcript references for RSEM.",
        [],
        [],
    ),
    Script(
        "00_sortmerna_indexing.sh",
        "Prepare rRNA index from rRNA fasta for SORTMERNA.",
        [],
        [],
    ),
    Script(
        "00_star_indexing.sh",
        "Prepare genome and transcriptome references for STAR.",
        [],
        [],
    ),
    Script(
        "01_sortmerna.sh",
        "Match reads to rRNA sequences to remove rRNA contamination.",
        [],
        [],
    ),
    Script(
        "02_star.sh",
        "Align reads to the genome and transcriptome.",
        [],
        [],
    ),
    Script(
        "03_rsem.sh",
        "Quantification of transcript expression.",
        [],
        [],
    ),
    Script(
        "03_sortIndexBam.sh",
        "Sort and index bam files from STAR.",
        [],
        [],
    ),
    Script(
        "04_getQCvalues.R",
        "Creates a table of quality control values from SORTMERNA, STAR, and RSEM.",
        [],
        [],
    ),
    Script(
        "05_DESeq2Template.R",
        "Template to show users how to import RSEM results into DESeq2 using tximport.",
        [],
        [],
    ),
]
