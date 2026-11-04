---
doc_id: ISP
title: Information Security Policy
version: 4.1
owner: Head of Security
last_reviewed: 2026-09-01
---

# Information Security Policy

## ISP-1 Purpose and scope
This policy sets the security requirements for Acme SaaS Ltd ("Acme") and the Acme Workspace platform, including the Acme Assist AI features. It applies to all employees, contractors and systems that store or process customer data.

## ISP-2 Security governance
The Head of Security owns the information security programme and reports to the CTO. A Security Steering Committee (CTO, Head of Security, Head of Engineering, Data Protection Officer) meets quarterly to review risks, incidents and policy exceptions. All security policies are reviewed at least annually.

## ISP-3 Certifications and attestations
Acme holds ISO/IEC 27001:2022 certification. The certificate scope covers the Acme Workspace platform and supporting operations at the London office. Acme completes an annual SOC 2 Type II audit covering the Security, Availability and Confidentiality trust services criteria. The SOC 2 report is available to customers and prospects under NDA.

## ISP-4 Personnel security
Background checks are carried out on all new hires before their start date, to the extent permitted by local law. All staff sign confidentiality agreements. Security awareness training is completed at onboarding and annually thereafter, and phishing simulations are run quarterly.

## ISP-5 Access control
Access follows the principle of least privilege. Multi-factor authentication is mandatory for all workforce accounts. Production access is granted through SSO with just-in-time elevation, is time-limited, and every session is logged. Access to production systems is reviewed quarterly. Leavers have access revoked within 24 hours of their departure. Customer-facing identity controls are described in the Identity, SSO & SCIM document (IAM).

## ISP-6 Encryption
Data in transit is encrypted using TLS 1.2 or higher, with TLS 1.3 preferred. Customer data at rest is encrypted with AES-256 using AWS Key Management Service. Encryption keys are managed by Acme and rotated annually.

## ISP-7 Vulnerability management
Dependencies are scanned automatically on every build, and container images are scanned before deployment. Remediation targets from discovery are: critical within 7 days, high within 30 days, medium within 90 days. An independent third party performs a penetration test of the application and infrastructure at least annually. An executive summary of the latest test is available to customers under NDA.

## ISP-8 Secure development
All code changes require peer review before merge. Static application security testing (SAST) runs in the CI pipeline. Development, staging and production environments are separated, and customer data is never used in non-production environments.

## ISP-9 Logging and monitoring
Security-relevant logs from infrastructure and applications are centralised and retained for 12 months. Alerts are monitored by an on-call engineering rota 24 hours a day, 7 days a week.

## ISP-10 Endpoint security
All company laptops are centrally managed, use full-disk encryption and run endpoint detection and response (EDR) software. Personal devices may not be used to access production systems.

## ISP-11 Exceptions
Exceptions to this policy must be approved by the Head of Security, recorded in the risk register, and reviewed at least every six months.
