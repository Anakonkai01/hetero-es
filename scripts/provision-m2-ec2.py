#!/usr/bin/env python3
"""Prepare/review a single CPU instance; apply only after live free-plan gates."""
import argparse
import importlib.util
import ipaddress
import json
from pathlib import Path
import sys


def request(config,eligible_type):
    if config['instanceType']!=eligible_type:raise ValueError('Selected type must match the live free-tier preflight')
    if not config['pricingReviewed'] or not config['billingAlertsConfigured']:raise ValueError('Complete live pricing and billing alert review')
    if type(config['rootVolumeGiB']) is not int or not 8<=config['rootVolumeGiB']<=30:raise ValueError('Root volume must be 8–30 GiB')
    return {'ImageId':config['imageId'],'InstanceType':config['instanceType'],'MinCount':1,'MaxCount':1,
        'KeyName':config['keyName'],'ClientToken':config['clientToken'],'CreditSpecification':{'CpuCredits':'standard'},
        'MetadataOptions':{'HttpTokens':'required','HttpEndpoint':'enabled'},
        'NetworkInterfaces':[{'DeviceIndex':0,'SubnetId':config['subnetId'],'Groups':[config['securityGroupId']],'AssociatePublicIpAddress':True}],
        'BlockDeviceMappings':[{'DeviceName':'/dev/sda1','Ebs':{'VolumeSize':config['rootVolumeGiB'],'VolumeType':'gp3','Encrypted':True,'DeleteOnTermination':True}}],
        'TagSpecifications':[{'ResourceType':'instance','Tags':[{'Key':'Name','Value':'heteroes-m2-control'}]}]}


def validate_security_group(sg):
    for permission in sg['IpPermissions']:
        if permission.get('IpProtocol')!='tcp' or permission.get('FromPort')!=permission.get('ToPort') or permission.get('FromPort') not in (22,80,443):raise ValueError('Unexpected public security-group rule')
        if permission.get('Ipv6Ranges'):raise ValueError('Review IPv6 rules before deployment')
        if permission['FromPort']==22:
            ranges=permission.get('IpRanges',[])
            if not ranges or any(ipaddress.IPv4Network(r['CidrIp']).prefixlen!=32 for r in ranges) or permission.get('UserIdGroupPairs') or permission.get('PrefixListIds'):
                raise ValueError('SSH must list explicit administrator IPv4 /32 addresses')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','apply']);p.add_argument('--config',required=True,type=Path);p.add_argument('--profile');a=p.parse_args()
    import boto3
    config=json.loads(a.config.read_text())
    spec=importlib.util.spec_from_file_location('preflight',Path(__file__).with_name('cloud-preflight.py'));preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(preflight)
    session=boto3.Session(profile_name=a.profile);gate=preflight.check_aws(session,config['region'])
    if not gate['ready']:raise SystemExit('An active FREE plan with credits and eligible instance is required; no Paid upgrade is attempted')
    ec2=session.client('ec2',region_name=config['region'])
    # Verify the dedicated group actually exposes only approved inbound ports.
    sg=ec2.describe_security_groups(GroupIds=[config['securityGroupId']])['SecurityGroups'][0]
    validate_security_group(sg)
    body=request(config,gate['selectedInstanceType'])
    if a.action=='plan':
        print(json.dumps({'gate':gate,'request':body,'provisionedResources':0},indent=2));return
    # ClientToken makes a repeated call after a lost response idempotent.
    result=ec2.run_instances(**body)
    print(json.dumps({'instanceIds':[r['InstanceId'] for r in result['Instances']],'region':config['region']}))

if __name__=='__main__':main()
