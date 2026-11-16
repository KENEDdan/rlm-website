# Choosing an online giving gateway

**Today:** giving works by **bank transfer / mobile money instructions + pledge form**, confirmed by Finance
(`ManualBankTransfer`). No card or wallet data ever touches the site.
**Later:** an online gateway plugs into `giving/providers/hosted_gateway.py` (a documented skeleton with
signature verification and idempotency already tested). Leave **Gateway enabled** off until then.

## Non-negotiable requirements (CLAUDE.md rule 11)

* **Hosted checkout only:** the donor types card/wallet details on the gateway's page, never ours.
* **Signed webhooks** (HMAC or similar) and a sandbox/test mode.
* Payouts to an account **owned by the ministry** (or its legal fiscal sponsor), with Finance as the only
  people able to change payout details, protected by 2FA on the gateway dashboard.
* Lawful for the ministry to receive funds from where donors live (sanctions/AML checks; see below).

## The honest situation (researched 2026-11-16)

A search for gateways that **onboard merchants registered in South Sudan** found no provider that clearly
confirms it. Several global gateways do not list South Sudan as a supported merchant country. Mobile money
is growing quickly: the Bank of South Sudan recognised mobile money as a legal form of payment in July 2025,
and MTN reports over one million active MoMo users there. So the realistic routes are below.
**Each claim must be confirmed directly with the provider in writing before any development work.**

## Three candidate routes

### 1. MTN Mobile Money "Collections" (local donors in South Sudan)
MTN's MoMo Open API has a *Collections* product (customer-approved debit requests, payment by USSD/app/web).
A third-party integrator lists South Sudan (`+211 92` numbers) among its supported MTN markets, which
suggests the API is available there.
**Verify with MTN South Sudan:** merchant/collections account for a registered ministry/NGO; API access in
South Sudan (not just Rwanda/Uganda); fees and payout schedule to the ministry's bank; callback signing
(MoMo callbacks need extra verification by querying the transaction status server-side, which the skeleton
supports: "never trust the redirect"); sandbox access. *m-Gurush* (Zain + Trinity Technologies) is the other
licensed wallet; no public merchant API was found. Ask them directly.

### 2. A regional card + mobile-money gateway through an East African entity
Gateways such as **Flutterwave**, **Pesapal** or **DPO Pay** serve East African merchants and accept cards
and regional wallets, but onboarding typically requires a company/NGO registered in a supported country
(e.g. Kenya or Uganda).
**Verify:** whether the ministry (or a registered partner) can onboard; South Sudan donors and
international cards accepted; NGO/donation category allowed; hosted checkout + signed webhooks; settlement
currency (USD?) and account location; KYC documents needed.

### 3. International donors through a fiscal sponsor or partner organisation
For donors abroad, many ministries receive gifts through a **registered charity or church in a supported
country** (e.g. US/UK/EU) acting as fiscal sponsor, using **Stripe Checkout** or **PayPal** in *that*
organisation's name, then granting funds to the ministry. This also lets donors receive tax receipts there.
**Verify:** a written fiscal-sponsorship agreement; who owns the gateway account and donor data (it becomes
their data too: privacy policy must say so); fees; how funds reach South Sudan legally.

## Compliance checks for any route

* **Sanctions:** some South Sudanese individuals and entities are on sanctions lists (e.g. the US OFAC South
  Sudan programme). Gateways and banks will screen the ministry; prepare registration documents, board list
  and a description of activities.
* **Anti-money-laundering:** expect KYC on the Founder and Finance officers.
* **Privacy:** update the privacy policy to name the gateway as a processor.

## When a gateway is chosen (developer checklist)

1. Implement `start_checkout` and `verify_webhook` in `giving/providers/hosted_gateway.py` exactly as its
   docstring describes; set the real signature/timestamp headers.
2. Add recorded, signed sample payloads from the gateway sandbox as tests.
3. Add the checkout origin to CSP `form-action` (and `frame-src` only if embedded).
4. Put the webhook secret in `.env` (`PAYMENT_WEBHOOK_SECRET`), never in code.
5. Test in sandbox end-to-end, then let Finance turn on **Gateway enabled**.

## Sources

* MTN MoMo developer products (Collections): https://momodeveloper.mtn.co.rw/products
* MTN MoMo South Sudan integration notes (third party): https://docs.powerlynx.app/finance/mtnmomo.html
* MTN and Digitel extend mobile money across South Sudan: https://techafricanews.com/2025/08/18/mtn-and-digitel-to-extend-mobile-money-services-across-south-sudan/
* South Sudan's first mobile money service (m-Gurush): https://nextbillion.net/news/two-companies-approved-to-run-south-sudans-first-mobile-money-platform-m-gurush
* m-Gurush international remittances: https://africa.com/headlines/south-sudans-first-mobile-money-service-launches-an-international-remittance-service
