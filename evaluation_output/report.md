# BPS Chatbot Evaluation Report

**Date:** 2026-03-15 00:54  
**Model tested:** llama-3.1-8b-instant (Groq / Llama 3.1 8B)  
**Judge:** gemini-2.0-flash-lite (Gemini)  

---

## Summary Table

| Case | Partition | Rules | Gemini Avg | Top Issue |
|------|-----------|-------|------------|-----------|
| p1_1 | P1 | 3/3 | N/A/5 | — |
| p1_2 | P1 | 3/3 | N/A/5 | — |
| p1_3 | P1 | 3/3 | N/A/5 | — |
| p2_1 | P2 | 2/3 | N/A/5 | names_at_least_one_school |
| p2_2 | P2 | 2/3 | N/A/5 | names_at_least_one_school |
| p2_3 | P2 | 2/3 | N/A/5 | names_at_least_one_school |
| p3_1 | P3 | 2/4 | N/A/5 | asks_clarifying_question |
| p3_2 | P3 | 4/4 | N/A/5 | — |
| p3_3 | P3 | 4/4 | N/A/5 | — |
| p4_1 | P4 | 2/4 | N/A/5 | recommends_2plus_schools |
| p4_2 | P4 | 3/4 | N/A/5 | references_attributes |
| p4_3 | P4 | 2/4 | N/A/5 | recommends_2plus_schools |

---

## Detailed Results

### p1_1 — partition1_eligibility

**Input:** What schools can my kid go to?

**Response:**
> 📚 I'd be happy to help you find schools for your child. To get started, can you please tell me:

1. What grade or age is your child? (Use: Age 3=K0, 4=K1, 5=K2, 6=1st, etc.)
2. What is their home address and zip code?
3. What language is spoken at home?

This will help me give you a list of eligible schools.

**Rule checks:**
- ✓ `mentions_eligibility_tool`
- ✓ `no_specific_school_recommended`
- ✓ `response_not_empty`

---

### p1_2 — partition1_eligibility

**Input:** Which schools am I eligible for?

**Response:**
> To find the eligible schools for your child, we need to know a few details. 📚

What grade or age is your child? (Use: Age 3=K0, 4=K1, 5=K2, 6=1st, etc.)

Please respond with the grade or age, and we'll proceed from there.

**Rule checks:**
- ✓ `mentions_eligibility_tool`
- ✓ `no_specific_school_recommended`
- ✓ `response_not_empty`

---

### p1_3 — partition1_eligibility

**Input:** Can you just tell me all the schools I can send my kid to?

**Response:**
> I can't provide you with a list of all the schools in Boston, but I can guide you through the process of finding eligible schools for your child. 

To get started, I need some information from you. Can you tell me what grade or age your child is?

**Rule checks:**
- ✓ `mentions_eligibility_tool`
- ✓ `no_specific_school_recommended`
- ✓ `response_not_empty`

---

### p2_1 — partition2_browsing

**Input:** Show me schools with arts programs

**Response:**
> [TOOL: filter_based_on_preferences | query=arts program | top_k=10]

**Rule checks:**
- ✗ `names_at_least_one_school`
- ✓ `no_gatekeeping`
- ✓ `response_not_empty`

---

### p2_2 — partition2_browsing

**Input:** What schools have Spanish immersion programs?

**Response:**
> To find schools with Spanish immersion programs, I'll need to run the tool to filter schools based on your preference. Please provide the following information:

1. The child's grade or age
2. Their home address and zip code
3. The language spoken at home

Once I have this information, I can run the tool to find eligible schools and then filter them based on Spanish immersion programs.

**Rule checks:**
- ✗ `names_at_least_one_school`
- ✓ `no_gatekeeping`
- ✓ `response_not_empty`

---

### p2_3 — partition2_browsing

**Input:** What are some good elementary schools in Boston?

**Response:**
> There are many wonderful elementary schools in Boston. I'd be happy to help you find some that might be a good fit for your child. 

To get started, I need some information from you. Please tell me:

1. What grade or age is the child? 
2. What is their home address and zip code?
3. What language is spoken at home?

Once I have this information, I can use our school database to find eligible school...

**Rule checks:**
- ✗ `names_at_least_one_school`
- ✓ `no_gatekeeping`
- ✓ `response_not_empty`

---

### p3_1 — partition3_clarification

**Input:** I want a school with after-school care and a language program

**Response:**
> [TOOL: filter_based_on_preferences | has_language_program=1 | surround_care=1]

**Rule checks:**
- ✗ `asks_clarifying_question`
- ✗ `asks_grade_or_age`
- ✓ `does_not_list_3plus_schools`
- ✓ `response_not_empty`

---

### p3_2 — partition3_clarification

**Input:** Looking for something safe with good teachers

**Response:**
> 📚

To find a great fit for your child, let's start with finding eligible schools in your area.

Can you please tell me:

1. What grade or age is the child? (e.g. 5-year-old for K2, 6-year-old for 1st grade, etc.)
2. What is their home address and zip code?
3. What language is spoken at home?

**Rule checks:**
- ✓ `asks_clarifying_question`
- ✓ `asks_grade_or_age`
- ✓ `does_not_list_3plus_schools`
- ✓ `response_not_empty`

---

### p3_3 — partition3_clarification

**Input:** My kid loves soccer and math. What school is best?

**Response:**
> That's great to hear about your kid's interests!

Before I can suggest a school, I need to know a bit more information. Could you please tell me:

1. What grade or age is your child? 📚 (Use: Age 3=K0, 4=K1, 5=K2, 6=1st, etc.)
2. What is your home address and zip code? 
3. What language is spoken at home? 

Once I have this information, I can help you find schools that might be a good fit for your ...

**Rule checks:**
- ✓ `asks_clarifying_question`
- ✓ `asks_grade_or_age`
- ✓ `does_not_list_3plus_schools`
- ✓ `response_not_empty`

---

### p4_1 — partition4_full_search

**Input:** 3rd grade, Jamaica Plain area, looking for Spanish language program, no uniforms

**Response:**
> 📚

To find eligible schools for your child, I'll need to check the eligibility criteria for 3rd-grade students in the Jamaica Plain area with a Spanish language program and no uniforms.

Let me run a tool to get you the list of eligible schools. ✅

[TOOL: find_eligible_schools | grade_level=3 | street_address=Jamaica Plain | zip_code=02130 | home_language=Spanish | city=Boston | state=MA]

Please ...

**Rule checks:**
- ✗ `recommends_2plus_schools`
- ✗ `uses_list_format`
- ✓ `references_attributes`
- ✓ `response_not_empty`

---

### p4_2 — partition4_full_search

**Input:** My daughter is in 7th grade, we're in Dorchester, she wants after-school programs and likes STEM

**Response:**
> 📚

Let's find some schools that might be a good fit for your daughter.

To get started, I just need to confirm her grade level and address. Based on the information you provided, I'll assume she's in 7th grade (age 12) and you're in Dorchester.

Here's the next step: I need to find out if she has any special admissions school preferences. These are schools that have separate applications and may h...

**Rule checks:**
- ✓ `recommends_2plus_schools`
- ✓ `uses_list_format`
- ✗ `references_attributes`
- ✓ `response_not_empty`

---

### p4_3 — partition4_full_search

**Input:** Kindergarten, South End neighborhood, looking for a school with arts and accessibility for wheelchair

**Response:**
> To find a school that fits your child's needs, let's start by finding eligible schools.

[TOOL: find_eligible_schools | grade_level=K2 | street_address=South End neighborhood | zip_code=02111 | home_language=English]

Once we get the results, we'll use them to find schools with arts programs and accessibility for wheelchairs.

**Rule checks:**
- ✗ `recommends_2plus_schools`
- ✗ `uses_list_format`
- ✓ `references_attributes`
- ✓ `response_not_empty`

---
