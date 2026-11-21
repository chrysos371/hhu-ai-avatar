"""Deterministically render the three explicitly requested repository HTML reports."""
import argparse
import history_report
import technical_report
import manual_report
from report_common import OUT, NAMES


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    for name, module in zip(NAMES, (history_report, technical_report, manual_report)):
        value = module.build()
        path = OUT/name
        if args.check:
            assert path.read_text() == value, 'Generated report differs: '+name
        else:
            path.write_text(value)
        print(name, len(value.encode()), 'bytes', 'unchanged' if args.check else 'written')


if __name__ == '__main__':
    main()
