"""Archive an immutable C55 group using the sealed, source-bound collector."""
import argparse
from reuse import load
# Load the current common first: the reused collector must bind C55 roots.
from execution_common import AUDIT,BASE,RUN,require


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['base','old_adapter','new_adapter'],required=True)
    p.add_argument('--repetition',type=int,choices=[1,2,3],required=True)
    args=p.parse_args();collector=load('collect_closed_group')
    require(collector.BASE==BASE and collector.RUN==RUN,'collector must bind fresh C55 roots')
    collector.AUDIT=AUDIT  # Explicit in-memory output root; old file bytes stay sealed.
    collector.main(args.stage,args.repetition)
