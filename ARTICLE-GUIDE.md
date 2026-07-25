<!-- BEGIN MANAGED ARTICLE GUIDE -->
# Article Guide — alat.berat.id

Status: repository-local instruction for expanding one prebuilt article outline at a time
Public route contract: `/artikel/[slug].html`
Source route evidence: sitemap XML, 3794 routes discovered during packet generation
Reader community name: `Berat.id`

## Exact prompt to give the lower-capability model

```text
Read AGENTS.md and ARTICLE-GUIDE.md completely. Expand only artikel/[EXACT-SLUG].md in place. Follow every scope, evidence, internal-link, and section instruction already inside that file. Do not edit any other file. Do not publish, hydrate HTML, update a sitemap, or push Git.
```

Replace `[EXACT-SLUG]` with one existing filename. Assign one article per run.

## Required reading order

1. `AGENTS.md`
2. this `ARTICLE-GUIDE.md`
3. exactly one assigned `artikel/[slug].md`

Do not load the portfolio ledger, OneDrive memory, another repository, the full catalog, or the full research file. The assigned outline already contains the needed local context.

## What the model must do

1. Confirm the assigned file's `article_id`, `title`, `slug`, primary intent, scope boundary, and final route.
2. Preserve front matter exactly except:
   - change `status: outline` to `status: draft` after the article is fully expanded;
   - set `date_modified` only when the user supplies or authorizes a real modification date;
   - add original source URLs only when actually used.
3. Replace instructional bullets under the detailed outline with finished Indonesian prose.
4. Answer the title's main question in the opening two or three paragraphs.
5. Keep every H2 focused on the distinct reader question stated beneath it.
6. Use original sources embedded in the evidence packet. Put the source link near the supported consequential claim.
7. Add internal links only where they help the reader take a next step. Use the exact routes already listed in the file.
8. Preserve every limitation, professional-review condition, and stop-work boundary.
9. Finish with a concrete next action or operating rule, not a generic summary.
10. Run the completion checklist inside the file before stopping.

## Writing style

- Write in clear Indonesian for a practical reader.
- Sound like a candid operator-teacher: direct answer first, mechanism next, evidence and decisions after that.
- Address the reader warmly as `Sobat Berat.id`, `Kawan Berat.id`, or `Teman Berat.id`. Use the exact opening salutation assigned inside the article file.
- Sprinkle these community addresses naturally three to five times in a typical long article, including the opening. Good positions are a consequential warning, a decision checkpoint, a practical example, and the conclusion. Do not force one into every section or repeat the same phrase in adjacent paragraphs.
- Use `Anda` naturally between those community-address moments. Use `saya` only when the outline contains real Syamsul-supplied experience.
- Vary sentence length. Prefer concrete actors, objects, actions, and consequences.
- Explain an English trade term on first use when Indonesian readers may not know it.
- Use a checklist, table, decision tree, warning, or scenario only when it reduces reader effort.
- Typical useful length is 1,400–2,200 words, but do not pad a complete answer.

## Evidence rules

- `GLOBAL_RESEARCH.md` was used to prepare the packet, but it is not a public source. Cite the original URLs embedded in the assigned article.
- A standards catalogue page proves identity/status/public scope only, not hidden clauses.
- A method does not prove a real product or project passed.
- A material property does not automatically prove installed-system performance.
- Foreign guidance is not Indonesian law.
- Project prices, capacity, availability, test results, warranties, measurements, and case outcomes require current project evidence.
- Keep `[NEEDS ...]` when the missing fact is consequential. Do not disguise uncertainty with confident wording.

## Internal-link rules

- Existing local routes in the assigned file are candidates; use only those that genuinely answer the next reader question.
- Planned sibling article routes are marked future. Do not link them as live until their source file is reviewed and the HTML route exists.
- Use descriptive natural anchors, not repeated exact-match keywords.
- Do not invent a route or add unrelated “Baca juga” links.
- Helpful density is welcome; link stuffing is not.

## Publication-date rule

The front matter's `publication_date` is the appointed historical CMS date. Preserve it exactly. Keep `publication_date_basis: editorial_backfill`. This is an intentional WordPress/CMS-style editorial workflow. Do not convert it to a future date.

## Never do

- Do not change the slug, article ID, parent topic, intent, or boundary.
- Do not claim Syamsul personally performed a project unless the file supplies that evidence.
- Do not invent quotes, statistics, prices, standards clauses, measurements, clients, or case studies.
- Do not copy an existing landing page or another article.
- Do not write generic openings such as “Di era digital” or “Seiring perkembangan zaman.”
- Do not mention SEO, keywords, AI, prompts, outlines, or evidence gates in public-facing prose.
- Do not edit more than the one assigned file.

## Definition of a completed draft

- The opening gives a direct answer.
- Every required section is expanded and non-repetitive.
- Consequential claims have original sources or visible review markers.
- Internal links are relevant and use exact local routes.
- No instruction bullets remain in the public article body.
- Front matter remains valid and `status` is `draft`.
- The draft ends with an actionable conclusion and honest boundary.

No HTML hydration, deployment, sitemap generation, or GSC submission is authorized by this guide.
<!-- END MANAGED ARTICLE GUIDE -->
