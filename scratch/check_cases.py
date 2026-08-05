import sys
sys.path.insert(0, '.')
import json
import glob
from src.csv_store import OlistStore
from src import case_pipeline

store = OlistStore('data')
files = sorted(glob.glob('input/EC_*.json'))

for f in files:
    c = json.load(open(f, encoding='utf-8'))
    cid = c['case_id']
    doc, errs = case_pipeline.solve_case(store, c)
    primary = doc['case_assessment']['primary_issue']
    secondary = doc['case_assessment']['secondary_issues']
    status = doc['case_assessment']['case_status']
    refund = doc['financial_resolution']['recommended_refund_brl']
    actions = doc['resolution_actions']
    parties = doc['root_cause_analysis']['responsible_parties']
    print(f"{cid}: primary={primary:<25} refund={refund:<8} status={status:<15} actions={actions}")
