# FinOps space walkthrough

This is a tour of the **finops** Kibana space on the GE Vernova observability project. The idea is simple: start with what AWS is actually costing, then look at where money might be saved, then look at Elastic’s own bill and AI usage, and finish with the alarms that watch those numbers.

Open the space at:

https://my-observability-project-f2e495.kb.us-west-2.aws.elastic.cloud/s/finops

## A few words that matter

**Identified** is money we think we can save each month. It only counts recommendations that are still open or being worked. Hidden items do not count.

**Captured** is money we already saved by finishing a change. Do not add Identified and Captured together. That would double-count: one is “still on the table,” the other is “already done.”

**Parked** is opportunity we chose to ignore for now (too risky, not feasible, or just a demo sample). It is not part of Identified.

AWS Cost Explorer can show the same bill several ways: by account, by product, by instance type, by availability zone. Those are slices of one bill, not extra piles of money. When someone asks “what did we spend?”, use the **linked-account** total. The product (service) view is useful, but it can miss lines that have no service name, so it is often a bit low.

Rightsizing savings will stay at **$0** until live AWS Compute Optimizer data is ingested. The sample recommendations in the space are parked on purpose so they do not fake a savings number.

---

## Dashboards

There are seven dashboards. Walk them in this order.

### 1. AWS Billing Overview

This is the bill. It defaults to the last 30 days and you can filter by account.

You will see cash-like spend (unblended) next to spend that includes Savings Plans and Reserved Instances (amortized). There is a daily chart by AWS product, and tables by account, product, instance type, and zone.

Use this board to answer “what did we spend?” and “which account or product is driving it?”

### 2. Spend vs savings

This puts the complete AWS bill next to the savings story.

The four headline numbers are: trailing spend, identified monthly savings, captured monthly savings, and parked savings. Under that you can see spend and opportunity by account, and opportunity by action (downsize, stop idle, and so on).

Until Compute Optimizer is flowing, identified will be empty and parked will show the four demo samples.

### 3. Rightsizing queue

This is the work list once real recommendations exist: what to change, from which size to which size, and about how much it would save.

The CPU table is not a recommendation. It is live CloudWatch evidence that some instances look idle. That is useful color, but it is not AWS Compute Optimizer.

The FilterLogEvents and ResourceCount panels are quota, not dollars. They exist because this account hits CloudWatch API limits; they are not a savings story.

Four demo cases sit in this space so the workflow is visible: one in progress (actions-runner), one open (ai-bridge), one closed (sample worker), and one parked as infeasible (idle disk).

### 4. AWS FinOps + Elastic Inference

This is the PoC overview. It combines AWS Cost Explorer with Elastic’s own assistant token usage (Kibana Agent Builder). It is **not** GE application or Bedrock LLM cost.

From here you can jump into the billing overview and the token dashboard.

### 5. Inference Token Usage

A packaged Elastic dashboard, copied into this space. It shows how many LLM tokens the Kibana assistant is using, by feature, model, and connector.

### 6 and 7. Elastic Cloud billing and credits

These are Elastic Cloud’s own bill for the observability project, not AWS. One board is usage, the other is credits.

---

## How to demo it

Start on Billing Overview and tell the bill. Move to Spend vs savings and say identified is still zero until Compute Optimizer is ingested. Open the Rightsizing queue and show the CPU evidence and the parked samples. Then show AWS FinOps + Inference if the conversation turns to Elastic’s own cost. Close with the two easiest guards: we page if the calendar month goes over **$77,000**, and if the stage account alone spends more than **$2,000** in a day.

---

## Alerts

Twelve rules are on. Most look at spend every hour. The SLO burn-rate rules look every minute.

**Month and 30-day spend.** If this calendar month’s AWS bill goes over $77,000, we alert. If the last 30 days go over $80,000, we alert. Those are slightly different windows on purpose (month-to-date vs a rolling month).

**Day-over-day spikes.** If the whole org’s daily spend jumps more than about 30% above recent days and is over $2,000, we alert. A second rule does the same at the product-and-account grain, with a lower bar ($100 and a 50% jump), so a noisy service in one account does not hide inside the org total.

**Stage account.** Account `985408759551` (apm-stage) should not spend more than $2,000 in a day.

**Broken billing view.** If the product slice of Cost Explorer is less than 90% of the linked-account total, we alert. That means the service table is incomplete; do not quote it as the bill.

**Elastic assistant.** If Agent Builder burns more than 20 million tokens in seven days, we alert.

**SLO burn.** Each budget SLO below has a companion rule. A slow leak pages on a three-day window. A faster leak pages within a day. A sharp spike pages within an hour.

Nothing yet pages on “identified savings is too high” or “Compute Optimizer recs arrived.” Those wait on a real feed.

---

## Budget SLOs

These are not uptime SLOs. They answer “did we stay inside the daily budget often enough over the last 30 days?” We want 95% of days at or under the ceiling.

- All linked AWS accounts together: **$3,000** a day.
- Stage (`985408759551`): **$2,000** a day.
- Monitoring account (`041298796264`): **$900** a day.
- The two ESF accounts together: **$800** a day.
- Elastic Agent Builder: **10 million** tokens a day.

They do not track whether anyone actually applied a rightsizing change.

---

## Demo cases

The four rightsizing cases are for the story, not production workflow. When live Compute Optimizer data lands, it will create new recommendation documents. This pass does not open a new case for every recommendation.
