#!/bin/bash
# Usage: ./upload.sh [-m "commit message"]

while getopts "m:" opt; do
    case $opt in
        m)
            commit_msg="$OPTARG"
            ;;
        *)
            echo "Usage: $0 [-m \"commit message\"]"
            exit 1
            ;;
    esac
done

# Default commit message if none provided
if [ -z "$commit_msg" ]; then
    commit_msg="minor fixes"
fi

git add .
git commit -m "$commit_msg"
git push