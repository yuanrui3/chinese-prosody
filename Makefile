PYTHON ?= python3

.PHONY: all test figures

all: test figures

test:
	$(PYTHON) -B -m unittest discover -s tests
	@for script in hpc/*.sbatch hpc/*.sh; do bash -n "$$script" || exit; done

figures:
	$(PYTHON) -B reports/build_figures.py
