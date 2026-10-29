#!/usr/bin/env bash
set -euo pipefail

demos_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uno_root="${UNO_SYNCFUSION_ROOT:-$(dirname "$demos_root")/uno-syncfusion}"
project="uno-ui-demos/Syncfusion.SampleBrowser.UNO/Syncfusion.SampleBrowser.UNO.csproj"

if [[ ! -f "$uno_root/$project" ]]; then
    echo "Uno sample browser not found at $uno_root/$project. Set UNO_SYNCFUSION_ROOT to your checkout." >&2
    exit 1
fi

cd "$uno_root"
export WINUI_DEMOS_ROOT="$demos_root"
dotnet build "$project" -f net10.0-desktop -c Release \
    -p:TargetFrameworks=net10.0-desktop \
    -p:UseUnoNuGetPackages=true \
    -p:UnoDisableHotDesign=true "$@"
