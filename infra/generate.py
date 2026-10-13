"""Generate reviewable CloudFormation JSON. No credentials or state in this repository."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def ref(name): return {'Ref': name}
def sub(value): return {'Fn::Sub': value}
def att(name, field): return {'Fn::GetAtt': [name, field]}
def resource(kind, properties, **extra): return {'Type': 'AWS::'+kind, 'Properties': properties, **extra}
def secret(name): return sub('{{resolve:secretsmanager:${'+name+'}:SecretString:token}}')
def visibility(name): return {'CloudWatchMetricsEnabled': True, 'SampledRequestsEnabled': False, 'MetricName': name}
def pathmatch(path):
    return {'ByteMatchStatement': {'SearchString': path, 'FieldToMatch': {'UriPath': {}},
        'PositionalConstraint': 'STARTS_WITH' if path.endswith('/') else 'EXACTLY',
        'TextTransformations': [{'Priority': 0, 'Type': 'NONE'}]}}

bootstrap = {'AWSTemplateFormatVersion': '2010-09-09',
    'Description': 'Marketplace Traffic Defence Lab: disposable image repository.',
    'Resources': {'Repository': resource('ECR::Repository', {'ImageTagMutability': 'IMMUTABLE',
        'ImageScanningConfiguration': {'ScanOnPush': True}, 'EmptyOnDelete': True,
        'Tags': [{'Key': 'Project', 'Value': 'marketplace-traffic-defence-lab'}]})},
    'Outputs': {'RepositoryUri': {'Value': att('Repository', 'RepositoryUri')}}}

template = {'AWSTemplateFormatVersion': '2010-09-09',
    'Description': 'Disposable marketplace: CloudFront/WAF, private ALB, two Fargate tasks, private encrypted Redis.',
    'Parameters': {
        'ImageUri': {'Type': 'String', 'AllowedPattern': '[A-Za-z0-9./:_@-]+'},
        'SourceCidr': {'Type': 'String', 'AllowedPattern': '[0-9.]+/32'},
        'AvailabilityZoneA': {'Type': 'AWS::EC2::AvailabilityZone::Name'},
        'AvailabilityZoneB': {'Type': 'AWS::EC2::AvailabilityZone::Name'},
        'CloudFrontPrefixList': {'Type': 'String', 'AllowedPattern': 'pl-[a-f0-9]+'},
        'ProbeMode': {'Type': 'String', 'AllowedValues': ['Count', 'Block'], 'Default': 'Count'}},
    'Conditions': {'EnforceProbe': {'Fn::Equals': [ref('ProbeMode'), 'Block']}},
    'Resources': {}, 'Outputs': {}}
r = template['Resources']
r['Vpc'] = resource('EC2::VPC', {'CidrBlock': '10.88.0.0/16', 'EnableDnsSupport': True, 'EnableDnsHostnames': True,
    'Tags': [{'Key': 'Project', 'Value': 'marketplace-traffic-defence-lab'}]})
r['Gateway'] = resource('EC2::InternetGateway', {})
r['GatewayAttachment'] = resource('EC2::VPCGatewayAttachment', {'VpcId': ref('Vpc'), 'InternetGatewayId': ref('Gateway')})
r['PublicRoutes'] = resource('EC2::RouteTable', {'VpcId': ref('Vpc')})
r['InternetRoute'] = resource('EC2::Route', {'RouteTableId': ref('PublicRoutes'), 'DestinationCidrBlock': '0.0.0.0/0',
    'GatewayId': ref('Gateway')}, DependsOn='GatewayAttachment')
for suffix, zone, public_cidr, private_cidr in [('A', 'AvailabilityZoneA', '10.88.1.0/24', '10.88.11.0/24'), ('B', 'AvailabilityZoneB', '10.88.2.0/24', '10.88.12.0/24')]:
    r['Public'+suffix] = resource('EC2::Subnet', {'VpcId': ref('Vpc'), 'AvailabilityZone': ref(zone), 'CidrBlock': public_cidr})
    r['Private'+suffix] = resource('EC2::Subnet', {'VpcId': ref('Vpc'), 'AvailabilityZone': ref(zone), 'CidrBlock': private_cidr})
    r['RouteAssociation'+suffix] = resource('EC2::SubnetRouteTableAssociation', {'SubnetId': ref('Public'+suffix), 'RouteTableId': ref('PublicRoutes')})
r['AlbGroup'] = resource('EC2::SecurityGroup', {'VpcId': ref('Vpc'), 'GroupDescription': 'CloudFront prefix only; internal ALB',
    'SecurityGroupIngress': [{'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'SourcePrefixListId': ref('CloudFrontPrefixList')}]})
r['AppGroup'] = resource('EC2::SecurityGroup', {'VpcId': ref('Vpc'), 'GroupDescription': 'Only ALB can reach application',
    'SecurityGroupIngress': [{'IpProtocol': 'tcp', 'FromPort': 8080, 'ToPort': 8080, 'SourceSecurityGroupId': ref('AlbGroup')}]})
r['RedisGroup'] = resource('EC2::SecurityGroup', {'VpcId': ref('Vpc'), 'GroupDescription': 'Redis private, only application clients',
    'SecurityGroupIngress': [{'IpProtocol': 'tcp', 'FromPort': 6379, 'ToPort': 6379, 'SourceSecurityGroupId': ref('AppGroup')}]})
for name in ('SessionSecret', 'OriginSecret', 'RedisSecret', 'LoginSecret'):
    r[name] = resource('SecretsManager::Secret', {'GenerateSecretString': {'SecretStringTemplate': '{}',
        'GenerateStringKey': 'token', 'PasswordLength': 40, 'ExcludePunctuation': True}})
r['RedisSubnets'] = resource('ElastiCache::SubnetGroup', {'Description': 'Private disposable Redis', 'SubnetIds': [ref('PrivateA'), ref('PrivateB')]})
r['Redis'] = resource('ElastiCache::ReplicationGroup', {'ReplicationGroupDescription': 'Lab shared limiter, one primary; no HA claim',
    'Engine': 'redis', 'EngineVersion': '7.1', 'CacheNodeType': 'cache.t4g.micro', 'NumCacheClusters': 1,
    'AutomaticFailoverEnabled': False, 'MultiAZEnabled': False, 'TransitEncryptionEnabled': True,
    'AtRestEncryptionEnabled': True, 'AuthToken': secret('RedisSecret'), 'SnapshotRetentionLimit': 0,
    'CacheSubnetGroupName': ref('RedisSubnets'), 'SecurityGroupIds': [ref('RedisGroup')]})
r['AppLogs'] = resource('Logs::LogGroup', {'RetentionInDays': 1})
r['WafLogs'] = resource('Logs::LogGroup', {'LogGroupName': sub('aws-waf-logs-${AWS::StackName}'), 'RetentionInDays': 1})
r['ExecutionRole'] = resource('IAM::Role', {'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [
    {'Effect': 'Allow', 'Principal': {'Service': 'ecs-tasks.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]},
    'ManagedPolicyArns': [sub('arn:${AWS::Partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy')],
    'Policies': [{'PolicyName': 'ReadLabSecrets', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
        {'Effect': 'Allow', 'Action': 'secretsmanager:GetSecretValue', 'Resource': [ref(n) for n in ('SessionSecret', 'OriginSecret', 'RedisSecret', 'LoginSecret')]}]}}]})
r['Cluster'] = resource('ECS::Cluster', {})
r['Task'] = resource('ECS::TaskDefinition', {'RequiresCompatibilities': ['FARGATE'], 'NetworkMode': 'awsvpc',
    'Cpu': '256', 'Memory': '512', 'RuntimePlatform': {'CpuArchitecture': 'X86_64', 'OperatingSystemFamily': 'LINUX'},
    'ExecutionRoleArn': att('ExecutionRole', 'Arn'), 'ContainerDefinitions': [{'Name': 'marketplace', 'Image': ref('ImageUri'),
        'Essential': True, 'ReadonlyRootFilesystem': True, 'PortMappings': [{'ContainerPort': 8080}],
        'Environment': [{'Name': 'REDIS_HOST', 'Value': att('Redis', 'PrimaryEndPoint.Address')}],
        'Secrets': [{'Name': name, 'ValueFrom': sub('${'+secret_name+'}:token::')} for name, secret_name in [
            ('SESSION_SECRET', 'SessionSecret'), ('ORIGIN_TOKEN', 'OriginSecret'), ('REDIS_PASSWORD', 'RedisSecret'), ('DEMO_LOGIN_PASSWORD', 'LoginSecret')]],
        'LogConfiguration': {'LogDriver': 'awslogs', 'Options': {'awslogs-group': ref('AppLogs'), 'awslogs-region': ref('AWS::Region'), 'awslogs-stream-prefix': 'app'}}}]})
r['Alb'] = resource('ElasticLoadBalancingV2::LoadBalancer', {'Scheme': 'internal', 'Type': 'application',
    'Subnets': [ref('PrivateA'), ref('PrivateB')], 'SecurityGroups': [ref('AlbGroup')],
    'LoadBalancerAttributes': [{'Key': 'deletion_protection.enabled', 'Value': 'false'}]})
r['Targets'] = resource('ElasticLoadBalancingV2::TargetGroup', {'VpcId': ref('Vpc'), 'Protocol': 'HTTP', 'Port': 8080,
    'TargetType': 'ip', 'HealthCheckPath': '/health', 'HealthCheckIntervalSeconds': 10, 'HealthyThresholdCount': 2,
    'TargetGroupAttributes': [{'Key': 'deregistration_delay.timeout_seconds', 'Value': '10'}]})
r['Listener'] = resource('ElasticLoadBalancingV2::Listener', {'LoadBalancerArn': ref('Alb'), 'Protocol': 'HTTP', 'Port': 80,
    'DefaultActions': [{'Type': 'forward', 'TargetGroupArn': ref('Targets')}]})
r['Service'] = resource('ECS::Service', {'Cluster': ref('Cluster'), 'TaskDefinition': ref('Task'), 'DesiredCount': 2,
    'LaunchType': 'FARGATE', 'HealthCheckGracePeriodSeconds': 30, 'DeploymentConfiguration': {
        'DeploymentCircuitBreaker': {'Enable': True, 'Rollback': True}, 'MaximumPercent': 200, 'MinimumHealthyPercent': 50},
    'NetworkConfiguration': {'AwsvpcConfiguration': {'AssignPublicIp': 'ENABLED', 'Subnets': [ref('PublicA'), ref('PublicB')], 'SecurityGroups': [ref('AppGroup')]}},
    'LoadBalancers': [{'ContainerName': 'marketplace', 'ContainerPort': 8080, 'TargetGroupArn': ref('Targets')}]},
    DependsOn=['Listener', 'InternetRoute', 'RouteAssociationA', 'RouteAssociationB'])
r['VpcOrigin'] = resource('CloudFront::VpcOrigin', {'VpcOriginEndpointConfig': {'Arn': ref('Alb'), 'Name': sub('${AWS::StackName}-origin'),
    'HTTPPort': 80, 'HTTPSPort': 443, 'OriginProtocolPolicy': 'http-only'}}, DependsOn=['GatewayAttachment', 'Listener'])
r['Sources'] = resource('WAFv2::IPSet', {'Scope': 'CLOUDFRONT', 'IPAddressVersion': 'IPV4', 'Addresses': [ref('SourceCidr')]})
rules = [
    {'Name': 'LabSourcesOnly', 'Priority': 0, 'Action': {'Block': {}}, 'Statement': {'NotStatement': {'Statement': {
        'IPSetReferenceStatement': {'Arn': att('Sources', 'Arn')}}}}, 'VisibilityConfig': visibility('LabSourcesOnly')},
    {'Name': 'SyntheticMarker', 'Priority': 1, 'Action': {'Block': {}}, 'Statement': {'ByteMatchStatement': {
        'SearchString': 'lab-block-me', 'FieldToMatch': {'SingleHeader': {'Name': 'user-agent'}},
        'PositionalConstraint': 'CONTAINS', 'TextTransformations': [{'Priority': 0, 'Type': 'NONE'}]}}, 'VisibilityConfig': visibility('SyntheticMarker')},
    {'Name': 'EnforcementProbe', 'Priority': 2, 'Action': {'Fn::If': ['EnforceProbe', {'Block': {}}, {'Count': {}}]},
        'Statement': {'RateBasedStatement': {'Limit': 10, 'EvaluationWindowSec': 60, 'AggregateKeyType': 'IP',
            'ScopeDownStatement': {'AndStatement': {'Statements': [pathmatch('/api/catalog'), {'ByteMatchStatement': {
                'SearchString': 'lab-rate-probe', 'FieldToMatch': {'SingleHeader': {'Name': 'user-agent'}}, 'PositionalConstraint': 'EXACTLY',
                'TextTransformations': [{'Priority': 0, 'Type': 'NONE'}]}}]}}}}, 'VisibilityConfig': visibility('EnforcementProbe')}]
recommendations = json.loads((ROOT/'site/data/recommendations.json').read_text())
for priority, proposal in enumerate(recommendations['proposals'], 10):
    if proposal['decision'] != 'propose_observation':
        continue
    edge = proposal['edge_proposal']
    rules.append({'Name': proposal['route'].title()+'Observe', 'Priority': priority, 'Action': {'Count': {}},
        'Statement': {'RateBasedStatement': {'Limit': edge['limit'], 'EvaluationWindowSec': 60,
            'AggregateKeyType': 'IP', 'ScopeDownStatement': pathmatch(edge['scope'])}}, 'VisibilityConfig': visibility(proposal['route']+'Observe')})
rules.append({'Name': 'JA4Observe', 'Priority': 30, 'Action': {'Count': {}}, 'Statement': {'RateBasedStatement': {
    'Limit': 30, 'EvaluationWindowSec': 60, 'AggregateKeyType': 'CUSTOM_KEYS', 'CustomKeys': [{'JA4Fingerprint': {'FallbackBehavior': 'NO_MATCH'}}],
    'ScopeDownStatement': pathmatch('/api/products/')}}, 'VisibilityConfig': visibility('JA4Observe')})
r['Waf'] = resource('WAFv2::WebACL', {'Scope': 'CLOUDFRONT', 'DefaultAction': {'Allow': {}}, 'Rules': rules, 'VisibilityConfig': visibility('MarketplaceLab')})
r['WafLogging'] = resource('WAFv2::LoggingConfiguration', {'ResourceArn': att('Waf', 'Arn'), 'LogDestinationConfigs': [att('WafLogs', 'Arn')],
    'RedactedFields': [{'SingleHeader': {'Name': name}} for name in ('authorization', 'cookie', 'x-lab-origin-token')]})
r['OriginPolicy'] = resource('CloudFront::OriginRequestPolicy', {'OriginRequestPolicyConfig': {'Name': sub('${AWS::StackName}-metadata'),
    'CookiesConfig': {'CookieBehavior': 'all'}, 'QueryStringsConfig': {'QueryStringBehavior': 'all'},
    'HeadersConfig': {'HeaderBehavior': 'allViewerAndWhitelistCloudFront', 'Headers': [
        'CloudFront-Viewer-Address', 'CloudFront-Viewer-ASN', 'CloudFront-Viewer-JA3-Fingerprint', 'CloudFront-Viewer-JA4-Fingerprint']}}})
r['Distribution'] = resource('CloudFront::Distribution', {'DistributionConfig': {'Enabled': True, 'Comment': 'Marketplace Traffic Defence Lab',
    'PriceClass': 'PriceClass_100', 'HttpVersion': 'http2', 'IPV6Enabled': False, 'WebACLId': att('Waf', 'Arn'),
    'Origins': [{'Id': 'marketplace', 'DomainName': att('Alb', 'DNSName'), 'VpcOriginConfig': {'VpcOriginId': att('VpcOrigin', 'Id')},
        'OriginCustomHeaders': [{'HeaderName': 'X-Lab-Origin-Token', 'HeaderValue': secret('OriginSecret')}]}],
    'DefaultCacheBehavior': {'TargetOriginId': 'marketplace', 'ViewerProtocolPolicy': 'https-only',
        'AllowedMethods': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'POST', 'PATCH', 'DELETE'], 'CachedMethods': ['GET', 'HEAD'],
        'CachePolicyId': '4135ea2d-6df8-44a3-9df3-4b5a84be39ad', 'OriginRequestPolicyId': ref('OriginPolicy')},
    'ViewerCertificate': {'CloudFrontDefaultCertificate': True}}})
for name, value in {'Endpoint': sub('https://${Distribution.DomainName}'), 'AppLogGroup': ref('AppLogs'),
    'WafLogGroup': ref('WafLogs'), 'LoginSecretArn': ref('LoginSecret'), 'WafArn': att('Waf', 'Arn'),
    'AlbScheme': 'internal', 'VpcOriginId': att('VpcOrigin', 'Id')}.items():
    template['Outputs'][name] = {'Value': value}
for name, value in [('bootstrap.json', bootstrap), ('lab.json', template)]:
    (ROOT/'infra'/name).write_text(json.dumps(value, indent=2)+'\n')
print('Generated bootstrap.json and lab.json with no credentials.')
