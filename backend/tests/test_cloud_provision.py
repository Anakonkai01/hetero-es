"""Review guards fail before any instance request or provider mutation."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('provision',Path(__file__).parents[2]/'scripts/provision-m2-ec2.py')
provision=importlib.util.module_from_spec(spec);spec.loader.exec_module(provision)


def test_unreviewed_or_ineligible_compute_cannot_generate_a_provisioning_request():
    config={'instanceType':'t3.small','pricingReviewed':True,'billingAlertsConfigured':True,'rootVolumeGiB':20,
        'imageId':'ami-test','keyName':'operator-key','clientToken':'stable-token','subnetId':'subnet-test','securityGroupId':'sg-test'}
    for change in ({'pricingReviewed':False},{'billingAlertsConfigured':False},{'instanceType':'g5.xlarge'},{'rootVolumeGiB':31}):
        with pytest.raises(ValueError):provision.request({**config,**change},'t3.small')


def test_ssh_sources_require_explicit_admin_addresses_and_only_web_ports_are_public():
    ssh={'IpProtocol':'tcp','FromPort':22,'ToPort':22,'IpRanges':[{'CidrIp':'203.0.113.7/32'}]}
    provision.validate_security_group({'IpPermissions':[ssh]})
    for changed in ({'IpRanges':[{'CidrIp':'0.0.0.0/0'}]},{'IpRanges':[{'CidrIp':'0.0.0.0/1'}]},
                    {'UserIdGroupPairs':[{'GroupId':'other-group'}]},{'FromPort':8000,'ToPort':8000},
                    {'Ipv6Ranges':[{'CidrIpv6':'::/0'}]}):
        with pytest.raises(ValueError):provision.validate_security_group({'IpPermissions':[{**ssh,**changed}]})
