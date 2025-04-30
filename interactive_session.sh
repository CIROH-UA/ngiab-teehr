#!/bin/bash
if [ "$1" == "run_teehr" ]; then
    python teehr_ngen.py
elif [ "$1" == "run_jupyter" ]; then
    # jupyter nbconvert --to notebook --execute /app/notebooks/test_notebook.ipynb
    jupyter lab --ip=0.0.0.0 --port=8888 --allow-root --notebook-dir=/app/notebooks --no-browser --NotebookApp.token='' --NotebookApp.password=''
else
    echo "Error: Invalid argument."
    exit 1
fi