#!/usr/bin/env python3
"""Read-only AWS/R2 gates. Does not provision resources or upgrade a plan."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def check_aws(session,region='ap-southeast-1'):
    plan=session.client('freetier',region_name='us-east-1').get_account_plan_state()
    expires=plan.get('accountPlanExpirationDate')
    credits=plan.get('accountPlanRemainingCredits',{}).get('amount',0)
    ready=plan['accountPlanType']=='FREE' and plan['accountPlanStatus']=='ACTIVE' and credits>0 and expires is not None and expires>datetime.now(timezone.utc)
    ec2=session.client('ec2',region_name=region)
    eligible=[]
    for page in ec2.get_paginator('describe_instance_types').paginate(Filters=[{'Name':'free-tier-eligible','Values':['true']}]):
        eligible.extend(r['InstanceType'] for r in page['InstanceTypes'])
    selected=next((t for t in ('t3.small','t3.micro') if t in eligible),None)
    return {'ready':bool(ready and selected),'planType':plan['accountPlanType'],'planStatus':plan['accountPlanStatus'],
            'remainingCredits':credits,'expiresAt':expires.isoformat() if expires else None,'region':region,
            'selectedInstanceType':selected,'cpuCredits':'standard','next':'Review live EC2/EBS/IPv4/transfer estimates and budget alerts before provisioning'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile');p.add_argument('--r2-config',type=Path);a=p.parse_args()
    import boto3
    from botocore.exceptions import ProfileNotFound
    try:
        session=boto3.Session(profile_name=a.profile)
        if session.get_credentials() is None:result={'aws':{'ready':False,'reason':'AWS login/profile is not configured'}}
        else:result={'aws':check_aws(session)}
    except Exception as error:
        result={'aws':{'ready':False,'errorType':type(error).__name__}}
    if a.r2_config:
        try:
            from backend.cloud_storage import S3Backend
            backend=S3Backend(json.loads(a.r2_config.read_text()))
            result['r2']={'ready':True,'existingBucketBytes':backend.inventory()}
        except Exception as error:result['r2']={'ready':False,'errorType':type(error).__name__}
    else:result['r2']={'ready':False,'reason':'Private R2 configuration is missing'}
    result['provisionedResources']=0
    print(json.dumps(result,indent=2))
    return 0 if result['aws']['ready'] and result['r2']['ready'] else 2

if __name__=='__main__':sys.exit(main())
