<p align="center">
  <img width="200" height="200" src="logo.svg" />
</p>

<p align="center">
    <a href="https://github.com/FGx-DCC/FGx_pipeline_wizard/actions/workflows/test.yml" alt="Test status">
      <img src="https://img.shields.io/github/actions/workflow/status/FGx-DCC/FGx_pipeline_wizard/test.yml?style=for-the-badge&label=tests&color=green" /></a>
    <a href="https://github.com/FGx-DCC/FGx_pipeline_wizard/blob/main/LICENSE" alt="License">
        <img src="https://img.shields.io/github/license/FGx-DCC/FGx_pipeline_wizard?style=for-the-badge&color=green" /></a>
</p>

# FGx Pipeline Wizard

This is a python package used by FGx pipelines to generate a single wrapper
script (*i.e.* `run.sh`) to execute all scripts that make up a pipeline (with
accompanying configuration file).

## Contents

* [Installation](#installation)
* [Usage](#usage)
* [Why this exists](#why-this-exists)
* [Idea](#idea)
* [How to use this](#how-to-use-this)
  * [Important things to note](#important-things-to-note)
* [Caveats and assumptions](#caveats-and-assumptions)

## Installation

First you will need:

- [python(>=3.15)](https://www.python.org/)
  - It is recommended to create a
    [conda](https://github.com/conda-forge/miniforge) environment (or
    equivalent, such as `uv`,`pixi`,`poetry`) for python, so that the package
    installation doesn't crowd your system python.
  - 3.15 is quite a recent version, so conda is likely a requirement anyways
    (system python probably isn't >=3.15). Some 3.15 features are used so this
    is indeed a requirement.

```bash
# Optionally create a conda environment first
conda create -n FGx_pipeline_wizard conda-forge::python==3.15 conda-forge::pip
conda activate FGx_pipeline_wizard

pip install "git+https://github.com/FGx-DCC/FGx_pipeline_wizard.git"
```

## Usage

This package isn't meant to be used by a user, but instead by a pipeline
developer. The intended route is the pipeline developer should create some
shell script to setup all requirements for the user (downloading environments,
libraries (*etc.*)) and then call on this tool (where it will know where the
scripts and pipelines are located) to get the user to generate their run script
and accompanying configuration file.

To run the tool, use:

```bash
pipeline_wizard \
  /path/to/scripts \
  /path/to/pipelines \
  /path/to/config_file \
  /path/to/run_script
```

You will likely find it useful to get the user to input where the run script
and config file should go.

## Why this exists

Are there other options out there? Yes, of course, there is nextflow and
snakemake and hundreds of other options. What sets this apart is that it tries
to make things easier for the user. Researchers (in my experience) don't like
to install a new tool to run a pipeline. So this assumes 1 thing, the user can
get python (conda is incredibly common in research contexts already).

The problem with something like nextflow or snakemake is that you need to write
your pipeline in the form the tool wants (granted, that's the case with this
tool, but I'm trying to make it as easy as possible). The other issue is that
a user wanting to run such a workflow needs said tool to run it too (which
sometimes isn't even possible). This tool provides pipeline creators with a
simple file format to create pipelines and then gives pipeline users a wizard
to generate a shell script they can execute like any other.

## Idea

- A user can select from a set of pipelines
- The user can then remove branches of the pipeline they don't need (perhaps
  they don't need to run fastqc on their files as this is already done)
- The user can also choose to start from any step in the pipeline (in case of a
  previous run failing perhaps)
- The user is then told which external files are required (and optional
  downloads can occur if files are missing)
- The user can then input any variables that scripts need (which is written to
  a configuration file, which set environment variables for shell scripts to
  use)
- A wrapper shell script to run the pipeline with accompanying configuration
  file is generated, which can be ran using bash.

A user is capable of changing the wrapper script or configuration file
themselves manually, but they may not be comfortable with this. For this
reason, the user may want to rerun this tool to update these files.

## How to use this

Pipelines are written in [toml](https://toml.io/en/) format, they bring
together individual scripts and declare parameters, external requirements and
script dependencies. Here's an example pipeline:

```toml
name = "Test Pipeline" # The name of the pipeline
description = "A test pipeline with read, clean and write steps" # short description
executor = "slurm" # slurm/pbs/local, omit if the user can choose

[parameters] # These will be global parameters, given as `key = value pairs`
OUT_DIRECTORY = "/path/to/output/directory/" # The key must be capitalised
KEEP_TEMPORARY = false # The value given for parameters is used as the default

[steps.read] # individual jobs are put under tags called [step.job_name]
path = "read.sh" # This is a relative path from 'scripts_directory' passed to the tool
description = "Read the data from a file and convert to pandas"

[steps.clean]
path = "clean.sh"
description = "Use interpolation to remove missingness"
after = ["read"] # This declares a dependency, it *must* be a list (and can contain multiple dependencies)

[steps.clean.requires] # This section declares externally required files
REFERENCE = "https://www.example.com/reference" # For example, this is a reference file with a download URL

[steps.clean.parameters] # This section declares parameters for this step only
MAX_DISTANCE = 5
TOOL_VERSION = ["v1", "v2"]

[steps.write]
path = "write.sh"
after = ["clean"]
[steps.write.parameters]
OUT_PATH = "/desired/path/to/output/"

[steps.report]
dag = "report.toml" # use 'dag = ...' to include a separate pipeline within this one (allowing for modularity)
after = ["write"]
```

### Important things to note

1. Script paths are relative to some 'scripts directory' (passed to tool).
2. 'dag' paths are relative to some 'pipelines directory' (passed to tool).
3. 'after' tags must result in an acyclic graph, if a dependency graph results
   in a cycle (implying some step is its own dependency) the tool will fail.
4. Parameters and requirements (`[step.name.requires]`) will be made made upper
   case in the configuration file. This is important as your scripts using
   these environment variables need to match the case (using 'out_dir' in a
   pipeline will lead to 'OUT_DIR' being set, not 'out_dir').
  - To make this less confusing, it is mandatory you write all parameters in
    the toml in upper case too.
  - This decision was made to stop complaints from linters like
    [shellcheck](https://www.shellcheck.net/).
  - This is important as it means if you have a pipeline with parameters like
  'paramname' and 'ParamName', these will be merged into one.
  - As these names are in upper case, please ensure you do not name any
    parameters after common environment variables like 'PATH' or 'HOME'.
5. Boolean parameters will be added as 'true' and 'false', these are used as
   most GNU/Linux systems have binaries called 'true' and 'false' that
   immediately exit with code 0/1 respectively.
6. The reason for having parameter sections for each job step and also globally
   is to reduce repetition for the pipeline creator. However, do not put all
   parameters into the global section. Job step parameter sections are still
   useful as it means if a user removes this step from the pipeline, they no
   longer are asked to provide a value for it.

## Caveats and assumptions

- Scripts that contain directives that are site specific (such as
  qos,account,nodelist (*etc.*)) should have these removed. The generator
  assumes that the site has defaults for each of these (possible on both slurm
  and pbs, but can be disabled). Inclusion of these will likely break your
  pipeline on other systems (as they won't have these resources).
- Scripts will obtain configuration parameters from the environment. The config
  file generated consists of lines like `export PARAMETER_NAME=value`. A
  reminder that all parameters will be capitalised when added to the
  configuration file.
- The local executor is highly basic and submits each job sequentially (rather
  than the parallel nature achieved easily with job schedulers).
- If no executor is specified it is assumed that the scripts are already
  written for either slurm or pbs and do not contain any variables that are
  specific to the job scheduler. For example, slurm has variables like
  '$SLURM_JOB_ID', there is currently nothing in place to translate this over
  to PBS or local.
  - Under this light, if your script uses anything specific to your scheduler,
    make sure to set the executor in the toml file for the pipeline.
- For slurm->pbs translation, there is no equivalent to filename patterns (like
  '%u' for user). As such these file names will be translated literally, keep
  this in mind if you want your pipeline to be transferrable.
- The PBS dialect chosen is PBS Pro (this would break arrays for example, where
  TORQUE uses `-t`, not `-J`).
