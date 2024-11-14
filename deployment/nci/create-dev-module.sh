#!/usr/bin/env bash

set -eou pipefail

this_dir="$(dirname "${0}")"
cd "$this_dir"

# Create in out dev module dir
export module_dir="/g/data/up71/modules"
export ard_product_array=${ard_product_array:="[\"LAMBERTIAN\", \"NBART\", \"NBAR\"]"}
./create-module.sh "${@}"
