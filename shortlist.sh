#!/bin/bash
# Fresh, eligible, ranked. Default: posted in the last 7 days.
# Pass a number to widen the window: ./shortlist.sh 14
DAYS="${1:-7}"
docker compose exec db psql -U careerops -d careerops -P pager=off -c "
SELECT round(fit_score::numeric,2) AS fit,
       company_name AS company,
       left(title, 45) AS title,
       date_part('day', now() - posted_at)::int AS age_d,
       apply_url
  FROM jobs
 WHERE closed_at IS NULL AND is_eligible
   AND posted_at > now() - interval '${DAYS} days'
 ORDER BY fit_score DESC
 LIMIT 20;"
