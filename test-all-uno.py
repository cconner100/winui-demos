#!/usr/bin/env python3
"""Run the Uno sample-browser catalog in fresh processes and retain each result."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--simulator', help='Booted iPad simulator UDID; install the app before running.')
parser.add_argument('--android', help='ADB serial of a booted Android emulator with the app installed.')
parser.add_argument('--start', type=int, default=1)
parser.add_argument('--end', type=int, default=10000)
parser.add_argument('--batch-size', type=int, default=20)
parser.add_argument('--screen-timeout', type=int, default=120)
args = parser.parse_args()
repo = Path(__file__).resolve().parent
uno = Path(os.environ.get('UNO_SYNCFUSION_ROOT', repo.parent / 'uno-syncfusion'))
exe = uno / 'uno-ui-demos/Syncfusion.SampleBrowser.UNO/bin/Release/net10.0-desktop/Syncfusion.SampleBrowser.UNO'
if not args.simulator and not args.android and not exe.is_file():
    parser.error('Build the desktop host first with ./build-uno.sh')
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
adb = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
if args.simulator and args.android:
    parser.error("Choose one device platform per run.")
if args.android:
    uid = subprocess.check_output([adb, '-s', args.android, 'shell', 'id', '-u'], text=True).strip()
    if uid != '0':
        parser.error('Run adb root on this test emulator before collecting private app artifacts.')
    resolved = subprocess.check_output([adb, '-s', args.android, 'shell', 'cmd', 'package', 'resolve-activity', '--brief', 'com.syncfusion.samplebrowser.uno'], text=True)
    activity = next(line.strip() for line in resolved.splitlines() if line.strip().startswith('com.syncfusion.samplebrowser.uno/'))
records = {}
start = args.start
attempt = 0
while start <= args.end:
    attempt += 1
    end = min(start + args.batch_size - 1, args.end)
    batch = output / f'{attempt:03d}-{start:03d}-{end:03d}'
    batch.mkdir()
    env = dict(os.environ, UNO_AUTO_SWEEP='1', UNO_SWEEP_START_INDEX=str(start),
               UNO_SWEEP_END_INDEX=str(end), UNO_SWEEP_SETTLE_MILLISECONDS='100',
               UNO_SWEEP_ARTIFACTS_DIR=str(batch), UNO_DISABLE_STUDIO='1')
    inventory = []
    rows = []
    last_count = 0
    changed = time.monotonic()
    reason = ''
    print(f'START {start}-{end} {batch}', flush=True)
    command = [str(exe)]
    if args.simulator:
        env.update({'SIMCTL_CHILD_' + key: value for key, value in env.copy().items() if key.startswith('UNO_')})
        command = ['xcrun', 'simctl', 'launch', '--terminate-running-process', '--console', args.simulator, 'com.syncfusion.samplebrowser.uno']
    if args.android:
        remote = '/data/user/0/com.syncfusion.samplebrowser.uno/files/uno-sweep/' + hashlib.sha256(str(output).encode()).hexdigest()[:12] + '/' + batch.name
        command = [adb, '-s', args.android, 'shell', 'am', 'start', '-W', '-S', '-f', '0x10008000', '-n', activity, '--es', 'autoSweep', '1', '--es', 'sweepStartIndex', str(start), '--es', 'sweepEndIndex', str(end), '--es', 'sweepSettleMilliseconds', '100', '--es', 'sweepArtifactsDir', remote]
    with (batch / 'process.log').open('w') as log:
        process = subprocess.Popen(command, cwd=uno, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while True:
                if args.android:
                    foreground = subprocess.check_output([adb, '-s', args.android, 'shell', 'dumpsys', 'activity', 'activities'], text=True)
                    top = next((line for line in foreground.splitlines() if 'topResumedActivity' in line), '')
                    if 'com.google.android.documentsui' in top or 'com.android.documentsui' in top:
                        subprocess.run([adb, '-s', args.android, 'shell', 'input', 'keyevent', '4'], stdout=log, stderr=log, timeout=10)
                    for artifact in ['screen-list.csv', 'results.csv', 'summary.txt']:
                        subprocess.run([adb, '-s', args.android, 'pull', remote + '/' + artifact, str(batch / artifact)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                inventory_path = batch / 'screen-list.csv'
                if inventory_path.exists():
                    with inventory_path.open() as f:
                        inventory = list(csv.DictReader(f))
                result_path = batch / 'results.csv'
                if result_path.exists():
                    with result_path.open() as f:
                        rows = [r for r in csv.DictReader(f) if r.get('Status')]
                if len(rows) > last_count:
                    for row in rows[last_count:]:
                        print(f"{row['Status']} {row['Control']} / {row['Screen']} {row['Reason']}", flush=True)
                    last_count = len(rows)
                    changed = time.monotonic()
                if (not args.android and process.poll() is not None) or (args.android and (batch / "summary.txt").exists()):
                    break
                if time.monotonic() - changed > args.screen_timeout:
                    reason = 'STALLED'
                    if args.android:
                        with (batch / 'stall.png').open('wb') as shot:
                            subprocess.run([adb, '-s', args.android, 'exec-out', 'screencap', '-p'], stdout=shot, stderr=log, timeout=15)
                    elif args.simulator:
                        subprocess.run(['xcrun', 'simctl', 'io', args.simulator, 'screenshot', str(batch / 'stall.png')], stdout=log, stderr=log, timeout=15)
                    else:
                        subprocess.run(['/usr/bin/sample', str(process.pid), '1', '-file',
                                        str(batch / 'stack.txt')], stdout=log, stderr=log, timeout=10)
                    break
                time.sleep(1)
        finally:
            if args.android:
                subprocess.run([adb, '-s', args.android, 'shell', 'am', 'force-stop', 'com.syncfusion.samplebrowser.uno'], stdout=log, stderr=log, timeout=15)
                subprocess.run([adb, '-s', args.android, 'pull', remote + '/.', str(batch)], stdout=log, stderr=log, timeout=120)
            if args.simulator:
                subprocess.run(['xcrun', 'simctl', 'terminate', args.simulator, 'com.syncfusion.samplebrowser.uno'], stdout=log, stderr=log, timeout=15)
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    if (batch / 'screen-list.csv').exists():
        with (batch / 'screen-list.csv').open() as final_inventory:
            inventory = list(csv.DictReader(final_inventory))
    if (batch / 'results.csv').exists():
        with (batch / 'results.csv').open() as final_results:
            rows = [row for row in csv.DictReader(final_results) if row.get('Status')]
    for entry, row in zip(inventory, rows):
        assert (entry['Control'], entry['Screen'], entry['View']) == (row['Control'], row['Screen'], row['View'])
        ordinal = start + int(entry['Ordinal']) - 1
        records[ordinal] = dict(entry, **{k: v for k, v in row.items() if k not in ('Index', 'Total')},
                                ArtifactDirectory=str(batch), GlobalOrdinal=ordinal)
    if len(rows) < len(inventory):
        entry = inventory[len(rows)]
        ordinal = start + int(entry['Ordinal']) - 1
        records[ordinal] = dict(entry, Status=reason or 'PROCESS_EXIT', Reason=f'exit={process.returncode}',
                                ArtifactDirectory=str(batch), GlobalOrdinal=ordinal)
        print(f"{records[ordinal]['Status']} {entry['Control']} / {entry['Screen']} ordinal={ordinal}", flush=True)
        start = ordinal + 1
    elif not inventory:
        if reason == 'STALLED' or (args.android and not (batch / 'summary.txt').exists()) or process.returncode != 0:
            raise RuntimeError(f'No inventory produced; inspect {batch}')
        break
    else:
        start += len(inventory)
        if len(inventory) < end - (start - len(inventory)) + 1:
            args.end = start - 1
    (output / 'results.json').write_text(json.dumps(list(records.values()), indent=2) + '\n')
    counts = {}
    for row in records.values():
        counts[row['Status']] = counts.get(row['Status'], 0) + 1
    print(f'CHECKPOINT tested={len(records)} counts={counts} next={start}', flush=True)
assert records, 'No screens were tested.'
assert sorted(records) == list(range(args.start, max(records) + 1)), 'Coverage gap.'
fields = sorted({key for row in records.values() for key in row})
with (output / 'results.csv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(records.values())
print(f'COMPLETE {output} screens={len(records)}', flush=True)
raise SystemExit(1 if any(row['Status'] != 'PASS' for row in records.values()) else 0)
