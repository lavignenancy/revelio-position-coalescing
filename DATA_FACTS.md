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