# Decisions I Made After Data Inspection

## D1: Handling company websites

I will need to standardize these URLs before comparing them to avoid treating the same company as two different companies. I will also check how many values are LinkedIn company URLs and how many are regular websites. This will help me decide what to include in the output and whether to keep the original URLs while using standardized versions for matching.

## D2: Handling observations from the same day

I will need to check for repeated positions within the same user and observation date. I will also compare their details to see whether they are duplicates or separate positions. From there, I can decide how to combine observations from the same day without losing useful information.

## D3: Handling incorrect employment dates

I will need to inspect these rows and check whether the errors affect individual positions or entire snapshots. I will also look at whether the same errors appear across multiple observations. My aim is to keep as much valid information as possible without carrying incorrect dates into the final output.

## D4: Identifying unrealistic employment dates

I will need to examine these records and compare their dates with the observation date and the person's available employment history. This will help me decide which dates are unrealistic and whether I should set specific limits instead of removing records based on assumptions.

## D5: Matching observations that belong to the same position

I will need to compare different combinations of fields to determine which ones provide the strongest evidence that two observations represent the same position. I am considering a scoring system that uses company names, URLs, titles, dates, and other available information.And I will also need to test cases where a person has held multiple positions at the same company to avoid incorrectly merging separate jobs.

## D6: Comparing employment dates

I will need to calculate how many start and end dates follow this pattern. If most dates use the first day of the month, I will consider comparing dates by month and year. This should help me avoid treating the same position as different jobs simply because of differences in date precision.