# BPS Chatbot Evaluation Report

**Date:** 2026-03-15 14:25  
**Model tested:** llama-3.1-8b-instant (Groq / Llama 3.1 8B)  
**Judge:** gemini-2.5-flash (Gemini)  

---

## Summary Table

| Case | Partition | Rules | Gemini Avg | Top Issue |
|------|-----------|-------|------------|-----------|
| p1_1 | P1 | 1/3 | 1.2/5 | mentions_eligibility_tool |
| p1_2 | P1 | 3/3 | 1.4/5 | — |
| p1_3 | P1 | 1/3 | 1.4/5 | mentions_eligibility_tool |
| p2_1 | P2 | 3/3 | 4.6/5 | — |
| p2_2 | P2 | 3/3 | 3.4/5 | — |
| p2_3 | P2 | 3/3 | 2.6/5 | — |
| p3_1 | P3 | 4/4 | 2.2/5 | — |
| p3_2 | P3 | 4/4 | 1.2/5 | — |
| p3_3 | P3 | 2/4 | 2.4/5 | asks_grade_or_age |
| p4_1 | P4 | 3/4 | 3.8/5 | recommends_2plus_schools |
| p4_2 | P4 | 4/4 | 1.0/5 | — |
| p4_3 | P4 | 4/4 | 1.8/5 | — |

---

## Detailed Results

### p1_1 — partition1_eligibility

**Input:** What schools can my kid go to?

**Response:**
> Boston has a wide range of excellent schools to choose from, depending on your child's age, interests, and your family's needs. Here are some options to consider:

**Public Schools:**

1. **Boston Public Schools (BPS)**: Boston's public school system offers a variety of programs, including bilingual schools, arts schools, and STEM-focused schools.
2. **Boston Latin School**: One of the oldest publ...

**Rule checks:**
- ✗ `mentions_eligibility_tool`
- ✗ `no_specific_school_recommended`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: ██░░░ 2/5
- accuracy: █░░░░ 1/5
- helpfulness: █░░░░ 1/5
- completeness: █░░░░ 1/5
- eligibility_handling: █░░░░ 1/5
- **Comments:** The chatbot completely failed to address school eligibility, which was central to the user's question, and instead recommended specific schools, violating key instructions. It also contained multiple factual inaccuracies and hallucinations regarding school names and locations (e.g., The Governor's Academy, The MFA School, Perkins School for the Blind location).

---

### p1_2 — partition1_eligibility

**Input:** Which schools am I eligible for?

**Response:**
> To determine which schools you're eligible for, I'll need some more information from you. 

Could you please provide the following details:

1. What is your current grade level (or age if you're entering a new school system)?
2. Do you live in Boston, MA, or the surrounding areas?
3. Are you looking for a public, private, or charter school?
4. Do you have any special needs or requirements (e.g., E...

**Rule checks:**
- ✓ `mentions_eligibility_tool`
- ✓ `no_specific_school_recommended`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: ███░░ 3/5
- accuracy: █░░░░ 1/5
- helpfulness: █░░░░ 1/5
- completeness: █░░░░ 1/5
- eligibility_handling: █░░░░ 1/5
- **Comments:** The chatbot correctly identifies that more information is needed to determine eligibility. However, it completely fails to mention the official BPS eligibility tool (discoverbps.org, avela, or bostonpublicschools.org) as required by the context. Instead, it incorrectly implies that the chatbot itself can provide a list of eligible schools, which is not how BPS eligibility works (it's based on home address and determined by the official tool). This makes the response inaccurate, unhelpful, and a critical failure in handling eligibility.

---

### p1_3 — partition1_eligibility

**Input:** Can you just tell me all the schools I can send my kid to?

**Response:**
> That's a big request. Boston has a wide range of public and private schools, each with its own unique features and qualities. I'd be happy to provide you with a comprehensive list, but keep in mind that this might be overwhelming.

Here's a general overview of the types of schools in Boston:

**Public Schools:**

1. Boston Public Schools (BPS) - a district with over 125 schools
2. Boston Charter S...

**Rule checks:**
- ✗ `mentions_eligibility_tool`
- ✗ `no_specific_school_recommended`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: ██░░░ 2/5
- accuracy: ██░░░ 2/5
- helpfulness: █░░░░ 1/5
- completeness: █░░░░ 1/5
- eligibility_handling: █░░░░ 1/5
- **Comments:** The response completely fails to address the user's core need regarding school eligibility. It does not mention the official eligibility tool (discoverbps.org, avela, or bostonpublicschools.org) as required. Furthermore, it incorrectly recommends specific schools, which is explicitly against the guidelines as eligibility depends on the home address. It also contains a significant factual error by listing Roxbury Latin School as a public school when it is a private institution. While it provides a general overview of school types, this information is not genuinely useful for a parent trying to find eligible schools for their child and is actively misleading.

---

### p2_1 — partition2_browsing

**Input:** Show me schools with arts programs

**Response:**
> Boston has a vibrant arts scene, and many schools offer excellent programs in music, dance, theater, and visual arts. Here are some schools with notable arts programs:

1. **Boston Latin School**:
	* Music: Concert bands, orchestras, choirs, jazz bands, and chamber music ensembles.
	* Dance: Annual dance performances, including ballet, modern, and hip-hop.
	* Theater: Productions of classical and ...

**Rule checks:**
- ✓ `names_at_least_one_school`
- ✓ `no_gatekeeping`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: █████ 5/5
- accuracy: ████░ 4/5
- helpfulness: █████ 5/5
- completeness: ████░ 4/5
- eligibility_handling: █████ 5/5
- **Comments:** The chatbot directly addresses the user's request by listing several real Boston Public Schools with arts programs. It provides a good overview of the types of arts offered at each. While some program descriptions are generic, the information is plausible and helpful as a starting point. It correctly avoids gatekeeping and advises further research, which is appropriate for browsing.

---

### p2_2 — partition2_browsing

**Input:** What schools have Spanish immersion programs?

**Response:**
> In Boston, here are some schools with Spanish immersion programs:

1. **Boston Latin School** - While not entirely Spanish immersion, it offers a Spanish language and culture program that allows students to take classes in Spanish and participate in cultural activities.
2. **O'Bryant High School** - Offers a Spanish immersion program that allows students to earn a high school diploma and a Spanish...

**Rule checks:**
- ✓ `names_at_least_one_school`
- ✓ `no_gatekeeping`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: █████ 5/5
- accuracy: █░░░░ 1/5
- helpfulness: ██░░░ 2/5
- completeness: ████░ 4/5
- eligibility_handling: █████ 5/5
- **Comments:** The response is highly relevant and correctly avoids gatekeeping, providing a good number of schools and acknowledging the list is not exhaustive. However, its accuracy is very poor. Rindge & Latin High School is in Cambridge, not Boston. Additionally, several Boston Public Schools (Boston International, Fenway, Madison Park, Boston Arts Academy) are incorrectly labeled as private or charter schools. These significant factual errors make the response misleading and unhelpful for a Boston parent.

---

### p2_3 — partition2_browsing

**Input:** What are some good elementary schools in Boston?

**Response:**
> Boston has a wide range of excellent elementary schools. Here are some highly-rated ones:

1. **Boston Latin School** (Elementary School Program is for grades K-4): While it's a well-known institution, they do offer an elementary program, although it's often considered more academically rigorous due to its history and preparation for the upper-level programs at Boston Latin.

2. **Higginson-Lewis ...

**Rule checks:**
- ✓ `names_at_least_one_school`
- ✓ `no_gatekeeping`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: █████ 5/5
- accuracy: █░░░░ 1/5
- helpfulness: █░░░░ 1/5
- completeness: ██░░░ 2/5
- eligibility_handling: ████░ 4/5
- **Comments:** The response directly addresses the user's question by listing schools. However, it contains critical factual errors: Boston Latin School and O'Bryant School are exam schools for grades 7-12, not K-4 or K-8. Listing them as elementary schools is highly misleading. Additionally, Citizens School is an after-school program provider, not a K-8 school, and Eliot-Pearson Children's School is a lab school at Tufts University, not a Boston Public School. These inaccuracies make the response actively unhelpful and potentially confusing for a parent. While it doesn't gatekeep, it fails to provide accurate or truly useful information.

---

### p3_1 — partition3_clarification

**Input:** I want a school with after-school care and a language program

**Response:**
> Boston has a wide range of schools that offer after-school care and language programs. Here are a few options to consider:

1. **Boston Latin School** (K-12): This highly-regarded public school offers a French, Spanish, and Chinese language program, as well as after-school care through its Extended Day Program.
2. **Boston Arts Academy** (9-12): This public high school focuses on the arts and offe...

**Rule checks:**
- ✓ `asks_clarifying_question`
- ✓ `asks_grade_or_age`
- ✓ `does_not_list_3plus_schools`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: ███░░ 3/5
- accuracy: ██░░░ 2/5
- helpfulness: ██░░░ 2/5
- completeness: ██░░░ 2/5
- eligibility_handling: ██░░░ 2/5
- **Comments:** The chatbot correctly identifies the need for clarifying questions but asks them *after* providing a broad list of schools, which goes against the context's requirement for a good response. The list includes a significant factual error regarding Boston Latin School's grade range (it's 7-12, not K-12) and a private school located outside Boston (The Cambridge School of Weston is in Weston, not Boston). This reduces accuracy and helpfulness. The initial recommendations are not tailored, making them less useful and incomplete for a parent seeking specific guidance.

---

### p3_2 — partition3_clarification

**Input:** Looking for something safe with good teachers

**Response:**
> As a Boston school finder assistant, I'd be happy to help you find a safe and well-regarded school in Boston. Here are some top-rated schools in various categories:

**Elementary Schools:**

1. **Dorchester's John W. McCormack Middle School** ( grades K-8) - 4.2/5 stars on GreatSchools.org, a highly-rated elementary school with a diverse student body and experienced teachers.
2. **Boston's Josiah ...

**Rule checks:**
- ✓ `asks_clarifying_question`
- ✓ `asks_grade_or_age`
- ✓ `does_not_list_3plus_schools`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: ██░░░ 2/5
- accuracy: █░░░░ 1/5
- helpfulness: █░░░░ 1/5
- completeness: █░░░░ 1/5
- eligibility_handling: █░░░░ 1/5
- **Comments:** The chatbot fails to follow the critical instruction to ask a clarifying question about grade level *before* recommending schools. Instead, it immediately provides a long list of schools across all levels. This list contains significant factual errors, including recommending a non-Boston Public School (New England Science and Sailing Foundation), miscategorizing school types (e.g., Boston Arts Academy as a middle school), and incorrect grade ranges. While it eventually asks a clarifying question, its placement after extensive, flawed recommendations makes the response highly unhelpful and misleading for a parent. The information provided is largely inaccurate and irrelevant without prior clarification.

---

### p3_3 — partition3_clarification

**Input:** My kid loves soccer and math. What school is best?

**Response:**
> I'd be happy to help you find a school that suits your child's interests in soccer and math. 

Considering Boston has many excellent schools, I'll suggest a few options that might fit your child's preferences:

1. **Boston Latin School**: Boston Latin is a highly academic public school that excels in math and science education. They have a strong athletic program, including soccer, with teams comp...

**Rule checks:**
- ✓ `asks_clarifying_question`
- ✗ `asks_grade_or_age`
- ✗ `does_not_list_3plus_schools`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: ███░░ 3/5
- accuracy: █████ 5/5
- helpfulness: ██░░░ 2/5
- completeness: █░░░░ 1/5
- eligibility_handling: █░░░░ 1/5
- **Comments:** The chatbot accurately describes several Boston schools that align with the user's stated interests (soccer and math). However, it critically fails to ask for the child's grade level or age before making recommendations, which is explicitly stated as a requirement in the context. This omission makes the recommendations potentially irrelevant and unhelpful, as school eligibility is entirely dependent on grade. It also lists 5 schools, which goes against the implicit rule of not listing too many without more information.

---

### p4_1 — partition4_full_search

**Input:** 3rd grade, Jamaica Plain area, looking for Spanish language program, no uniforms

**Response:**
> You're looking for a great 3rd-grade school in Jamaica Plain that offers a Spanish language program and doesn't have uniforms. Based on your criteria, here are some options to consider:

1. **Holland Elementary School**: Located at 85 Seaverns Ave, Jamaica Plain, MA 02130. Holland Elementary offers a bilingual program with a focus on Spanish, but it's not exclusively a Spanish immersion program. T...

**Rule checks:**
- ✗ `recommends_2plus_schools`
- ✓ `uses_list_format`
- ✓ `references_attributes`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: ████░ 4/5
- accuracy: ███░░ 3/5
- helpfulness: ████░ 4/5
- completeness: ███░░ 3/5
- eligibility_handling: █████ 5/5
- **Comments:** The chatbot provided a good list of schools that largely fit the user's criteria, including specific program types and uniform policies, and offered appropriate next steps. However, it made a significant error by recommending Franklin Park Zoo School, which is not located in the Jamaica Plain area as requested. This geographical inaccuracy impacts the accuracy, relevance, and completeness of the response.

---

### p4_2 — partition4_full_search

**Input:** My daughter is in 7th grade, we're in Dorchester, she wants after-school programs and likes STEM

**Response:**
> As a helpful Boston school finder assistant, I'd be happy to assist you in finding suitable schools for your daughter in Dorchester that fit her interests in STEM and after-school programs.

Dorchester is a diverse neighborhood in Boston with a range of schools that cater to different interests and needs. Here are some schools in Dorchester that offer STEM programs and after-school activities:

1....

**Rule checks:**
- ✓ `recommends_2plus_schools`
- ✓ `uses_list_format`
- ✓ `references_attributes`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: █░░░░ 1/5
- accuracy: █░░░░ 1/5
- helpfulness: █░░░░ 1/5
- completeness: █░░░░ 1/5
- eligibility_handling: █░░░░ 1/5
- **Comments:** The response recommends a non-existent school ('Dorchester High School' closed in 1982) and several high schools (Madison Park, BDEA) for a 7th grader, which is completely inappropriate for the user's daughter's grade level. While it attempts to list schools and address preferences, the fundamental errors in school existence and grade-level eligibility make the entire response irrelevant, inaccurate, and unhelpful. The descriptions of STEM and after-school programs are also generic and likely boilerplate.

---

### p4_3 — partition4_full_search

**Input:** Kindergarten, South End neighborhood, looking for a school with arts and accessibility for wheelchair

**Response:**
> The South End is a vibrant neighborhood in Boston with a rich cultural scene and diverse community. For a kindergarten with arts and accessibility for a wheelchair, I'd be happy to recommend some schools. Here are a few options:

1. **Boston Arts Academy** (BAA) - While not exclusively a kindergarten, BAA is a highly-regarded public arts high school with a strong focus on arts education. They offe...

**Rule checks:**
- ✓ `recommends_2plus_schools`
- ✓ `uses_list_format`
- ✓ `references_attributes`
- ✓ `response_not_empty`

**Gemini scores:**
- relevance: ██░░░ 2/5
- accuracy: █░░░░ 1/5
- helpfulness: ██░░░ 2/5
- completeness: ██░░░ 2/5
- eligibility_handling: ██░░░ 2/5
- **Comments:** The chatbot correctly identifies two suitable elementary schools (John F. Kennedy and Manning) that match the user's criteria for Kindergarten, arts, accessibility, and neighborhood. However, it makes significant errors by recommending Boston Arts Academy (a high school) and misrepresenting Boston Latin School's K-8 program (which is actually a separate charter school, Latin Academy Preparatory Charter School, and not directly part of BLS). These inaccuracies make half of the recommendations irrelevant and misleading for a parent seeking a Kindergarten program, severely impacting accuracy and helpfulness.

---
