## Observations I made while conducting Data Inspection

While inspecting the dataset, I noticed a few things that are different from what was described in the assignment PDF: 


1. A difference in the columns mentioned in the assignment. In the assignment it mentions company_linkedin_url however the actual data has company_website. I will need to look at the contents of this column to see if they are LinkedIn URLs or general company websites before deciding how to handle them in the output.

2. While looking at one user's observations, I noticed that the same company's LinkedIn URL was written in two different formats. Most of the observations used linkedin.com/company/seiwa-optical-america-inc-, but one included https://www. at the beginning. Even though the URLs look slightly different, they refer to the same company page. This made me realize that I need to clean and standardize the URLs before comparing them.

3. The observed_ts is stored as DATE so I will not be able to see when exactly the profile was observed just only what day. There may also be duplicate records if the user had more than one scrape on the same day.

4. The assignment mentions that there are around 10 million rows of observations however there are 11,480,179 rows in the dataset when I downloaded it.

5. There are 150,000 users and about 3.94 million snapshots. This means that there are around 26 snapshots per person. This stood out to me because it means I'll be comparing the same person's work history many times, and I need to make sure I don't treat an existing job as a new one every time it appears.

6. Both startdate and enddate are already stored as DATE values, so I won't need to convert them. However, I want to check if most of the dates fall on the first day of the month, as this could mean that the original data only recorded the month and year rather than the exact date.

7. I also noticed that a lot of values are missing from the dataset. The description column has 63.65% missing values, location has 45.75%, and company websites have 43.62%. This means I can't rely on just one column when trying to identify the same position across different observations. I'll need to compare several details to make a better decision.

8. Another thing I noticed is that 2,676 rows have an enddate that comes before the startdate. There are also a few records with very old start dates or dates that are later than when the profile was observed. Before removing any of these records, I want to understand whether the issue is with just one position or the entire observation. I don't want to throw away useful information because of one incorrect value.

9. After checking the company_website column, I found that all the non-empty values are LinkedIn URLs, even though the column has a different name from what the assignment describes. About 43.6% of the values are missing. 

10. I noticed another difference between the assignment and the actual dataset. The PDF says that order_in_profile starts at 0, but in all 3,941,416 snapshots, the positions start at 1. This is something I will need to consider if I use the position order when comparing observations.

11. I found that 75,654 snapshots, which is about 1.92%, contain less than half the number of positions a user normally has. This suggests that some scrapes are incomplete. I will need to make sure that positions don't disappear from the reconstructed history just because a later scrape collected fewer jobs.

12. Some records have very little information. I found 62,082 rows that contain a company name but no other position details, and 4,047 rows that have neither a company name nor a job title. This means I cannot require every position to have a job title before trying to match it. I will need to decide how much information is enough to identify a position reliably.

13. I also noticed that some fields contain placeholders rather than actual names or titles. For example, `-` appears 32,585 times and `.` appears 1,689 times. However, I also found short names like EY, HP, GE, 3M, and TD, which are real company names, as well as titles like RN, MD, and IT. Because of this, I shouldn't remove values just because they are short. I also came across titles written in Chinese, so I will need to make sure the text cleaning doesn't remove characters from other languages.

14. I found 55,857 cases where the same company and start date were associated with different job titles. This suggests that job titles can change between observations, although I still need to check whether these are title edits or separate positions. I shouldn't rely on an exact title match alone when deciding whether two observations represent the same job.

15. Another interesting finding was that 154,506 cases appear to contain the same position more than once within a single snapshot. I'm not sure yet whether this happens because the profile was scraped multiple times on the same day or because the position was listed more than once. I will need to look at actual examples before deciding how to handle these duplicates.