import sys
sys.path.insert(0, '.')
import json
import glob
from src import policy_engine
from src.csv_store import OlistStore
from src import case_pipeline

store = OlistStore('data')
files = sorted(glob.glob('input/EC_*.json'))

diff_count = 0
for f in files:
    c = json.load(open(f, encoding='utf-8'))
    cid = c['case_id']
    
    old_out = policy_engine.evaluate_case(c)
    new_out, errs = case_pipeline.solve_case(store, c)
    
    diffs = []
    if old_out['case_assessment']['primary_issue'] != new_out['case_assessment']['primary_issue']:
        diffs.append(f"primary: old={old_out['case_assessment']['primary_issue']} vs new={new_out['case_assessment']['primary_issue']}")
    if old_out['case_assessment']['secondary_issues'] != new_out['case_assessment']['secondary_issues']:
        diffs.append(f"secondary: old={old_out['case_assessment']['secondary_issues']} vs new={new_out['case_assessment']['secondary_issues']}")
    if old_out['financial_resolution']['recommended_refund_brl'] != new_out['financial_resolution']['recommended_refund_brl']:
        diffs.append(f"refund: old={old_out['financial_resolution']['recommended_refund_brl']} vs new={new_out['financial_resolution']['recommended_refund_brl']}")
    if old_out['resolution_actions'] != new_out['resolution_actions']:
        diffs.append(f"actions: old={old_out['resolution_actions']} vs new={new_out['resolution_actions']}")
    if old_out['evidence_ids'] != new_out['evidence_ids']:
        diffs.append(f"evidence: old={old_out['evidence_ids']} vs new={new_out['evidence_ids']}")
        
    if diffs:
        diff_count += 1
        print(f'{cid}:', ' | '.join(diffs))

print(f'Total cases with differences between engines: {diff_count} / 50')
