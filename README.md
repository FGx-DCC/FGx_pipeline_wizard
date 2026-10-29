# FGx Pipeline Wizard

This is a python package used by FGx pipelines to generate a single script
(`run.sh`) to execute all scripts that make up a pipeline (with accompanying
configuration file).

## Contents

* [Installation](#installation)
* [Idea](#idea)
* [toml format for pipelines](#toml-format-for-pipelines)
* [Assumptions](#assumptions)

## Installation

First you will need:

- [python(>=3.15)](https://www.python.org/)
  - It is recommended to create a
    [conda](https://github.com/conda-forge/miniforge) environment (or
    equivalent) for python, so that the installation doesn't crowd system
    python.

```bash
# Optionally create a conda environment first
conda create -n FGx_pipeline_wizard conda-forge::python conda-forge::pip
conda activate FGx_pipeline_wizard

pip install "git+https://github.com/FGx-DCC/FGx_pipeline_wizard.git"
```

## Idea

- A user can select from a set of pipelines (or create their own)
- The user can then remove branches of the pipeline they don't need (perhaps
  they don't need to run fastqc on their files as this is already done)
- The user can also choose to start from any step in the pipeline (in case of a
  previous run failing perhaps) and also end prematurely (if later steps aren't
  required for their experiment)
- The user is then told which external files are required (and optional
  downloads can occur if files are missing)
- The user can then input any variables that scripts need (which is written to
  a configuration file, which set environment variables for shell scripts to
  use)
- A `run.sh` and configuration file is generated, which can be ran using bash.

A user is capable of changing the `run.sh` or configuration file themselves
manually, but they may not be comfortable with this. For this reason, the user
may want to rerun this tool to update these files.

## toml format for pipelines

Pipelines are written in [toml](https://toml.io/en/) like so:

```toml
name = "Test Pipeline"
description = "A test pipeline with read, clean and write steps"

[parameters]
out_directory = "/path/to/output/directory/"
keep_temporary = false

[steps.read]
path = "read.sh"
description = "Read the data from a file and convert to pandas"

[steps.clean]
path = "clean.sh"
description = "Use interpolation to remove missingness"
requires = ["https://www.example.com/reference"]
after = ["read"]
[steps.clean.parameters]
max_distance = 5
tool_version = ["v1", "v2"]

[steps.write]
path = "write.sh"
after = ["clean"]
[steps.write.parameters]
out_path = "/desired/path/to/output/"

[steps.report]
dag = "report.toml"
after = ["write"]
```

Key:

- Sections are denoted by `[steps.step_name]`
- path -> The path (relative to some scripts directory) the script lies
- description -> The description of the pipeline (top) or step
- after -> What scripts need to complete successfully for this one to run (a
  prerequisite)
- requires -> An external file that is required (for example, a genome fasta)
- dag -> A path to another toml to embed into this one (allows for more
  flexibility and modularity)
- Parameters -> Denoted in `key = value` pairs under section header
  `[steps.step_name.parameters]`
  - The value given is considered a default. The user will be asked if they
    wish to override this.
  - If a list is given for value (`[option_1, option_2]`), the user will be
    given this list of options to choose from (rather than trying to guess at a
    different value)
  - All parameters when added into the configuration file will be made upper
    case. This decision was made to stop complaints from linters like
    [shellcheck](https://www.shellcheck.net/).
- `[parameters]` -> This is a section for defining parameters that are used in
  multiple scripts. It is also given as key value pairs like above.
  - It is not recommended to use this for one off cases as users can remove
    branches they don't need. If a parameter is only used in a single script
    (and that script is removed from the pipeline), it should go under that
    particular script (not the global parameters), else the user would need to
    set a value that is never used.

## Assumptions

- The [slurm workload manager](https://slurm.schedmd.com/) is used as a job
  executor in the scripts being ran
  - Under this light, all scripts in the pipeline being generated are expected
    to run if called with `sbatch` (meaning they need a shebang and #SBATCH
    directives)
- Scripts will obtain configuration parameters from the environment. The config
  file generated consists of lines like `export PARAMETER_NAME=value`. A
  reminder that all parameters will be capitalised when added to the
  configuration file.
