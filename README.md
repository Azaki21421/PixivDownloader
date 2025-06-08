# PixivDownloader
A robust Python script for downloading artworks from Pixiv, supporting single artwork posts and entire user galleries. It leverages Pixiv's internal APIs for reliable data extraction and uses multi-threading for faster downloads.

# Table of Contents
- [Features](#features)

- [Prerequisites](#prerequisites)

- [Installation](#installation)

- [Usage](#usage)

  - [Setting up PHPSESSID](#setting-up-phpsessid)

  - [Downloading a Single Artwork](#downloading-a-single-artwork)

  - [Downloading a User's Gallery](#downloading-a-users-gallery)

- [Important Notes](#important-notes)

- [Troubleshooting](#troubleshooting)

- [License](#license)

# Features
- **Single Artwork Download**: Download all images from a specific Pixiv artwork URL.

- **User Gallery Download**: Download all artworks (illustrations and manga) from a Pixiv user's profile.

- **Flexible Output**: Option to download user's artworks into separate folders per post or all into one root folder.

- **Automated Archiving**: Automatically zips downloaded content for easy management.

- **Multi-threaded Downloads**: Utilizes concurrent connections to significantly speed up image downloading.

- **Interruption Handling**: Safely stop the download process at any time (Ctrl+C) and archive partially downloaded files.

- **API-driven Data Extraction**: Prioritizes Pixiv's internal AJAX APIs for more reliable title and image URL fetching, mitigating issues with dynamic HTML selectors.

- **Fallback Mechanism**: Includes a fallback to HTML parsing for image URLs if API calls fail.

# Prerequisites
Before you begin, ensure you have the following installed:

- **Python 3.7+**: Download from python.org.

# Installation
1. Clone this repository (or download the pixiv_downloader.py file):

```
git clone [https://github.com/Azaki21421/PixivDownloader.git](https://github.com/Azaki21421/PixivDownloader.git)
cd PixivDownloader
```

2. Install the required Python libraries:
```
pip install requests beautifulsoup4 tqdm
```
# Usage
## Setting up PHPSESSID
Pixiv employs various anti-bot measures and content restrictions (especially for R-18 content). Providing a valid PHPSESSID from a logged-in Pixiv account significantly improves download success rates and bypasses many restrictions.

1. Open your web browser (preferably Chrome or Firefox).

2. Go to https://www.pixiv.net/ and log in to your Pixiv account.

3. Once logged in, open Developer Tools (usually by pressing F12).

4. Navigate to the Application tab (or Storage -> Cookies in some browsers).

5. In the left sidebar, expand Cookies and select https://www.pixiv.net.

6. Find the cookie named PHPSESSID.

7. Copy the entire value of this cookie.

8. Open the pixiv_downloader.py file in a text editor.

9. Locate the line PHPSESSID = "" and paste your copied value between the double quotes:
```
PHPSESSID = "YOUR_COPIED_PHPSESSID_VALUE_HERE"
```
10. Save the file.

## Running the Script
Open your terminal or command prompt, navigate to the directory where you saved pixiv_downloader.py, and run:
```
python pixiv_downloader.py
```
The script will then prompt you to enter a Pixiv link.

## Downloading a Single Artwork
Enter the URL of a single Pixiv artwork post (e.g., https://www.pixiv.net/en/artworks/123456789).
```
Enter Pixiv link (artwork post or user profile): https://www.pixiv.net/en/artworks/123456789
```
The script will download all images from that post into a folder named after the artwork's title and then zip the folder.

## Downloading a User's Gallery
Enter the URL of a Pixiv user's profile (e.g., https://www.pixiv.net/en/users/123456).
```
Enter Pixiv link (artwork post or user profile): https://www.pixiv.net/en/users/123456
Download into separate folders for each post? (y/n): y
```
You'll be asked if you want to download artworks into separate subfolders for each post (y) or all into one flat folder (n).

- If y, artworks will be downloaded into Pixiv_User_ID/Post_Title_1/, Pixiv_User_ID/Post_Title_2/, etc.

- If n, all artworks will be downloaded directly into Pixiv_User_ID/.

After all downloads are complete, the entire Pixiv_User_ID folder will be zipped.

## Stopping the Process
You can press Ctrl+C at any time during the download process. The script will catch the interruption, attempt to archive any partially downloaded files/folders, and then exit cleanly.

# Important Notes
- **PHPSESSID**: As mentioned, keeping your PHPSESSID up-to-date is crucial for consistent success, especially for R-18 content or to avoid rate limits. If you experience JSONDecodeError with HTML content in the raw response, your PHPSESSID is the first thing to check.

- **Pixiv's Anti-Bot Measures**: Pixiv continuously updates its website and API endpoints to deter automated scraping. While this script uses robust API calls, these can change. If the script stops working, it's likely due to Pixiv's changes. So open "issue" if this happened and i will change code.

- **Dynamic IDs**: Pixiv often uses dynamically generated IDs (e.g., _next/data/BUILD_ID/) which this script attempts to extract on the fly for specific artwork JSONs. If the method of extracting these IDs changes, parse_post might break.

- **Rate Limiting**: Even with multi-threading, rapid successive API calls can trigger temporary IP bans or CAPTCHAs. Small delays are built in, but if you're scraping a very large number of artworks or users, you might need to increase the time.sleep() values.

# Troubleshooting
- **JSONDecodeError: Expecting value: line 1 column 1 (char 0)**:

  - **Cause**: Pixiv returned an HTML page (like a login page, CAPTCHA, or error page) instead of valid JSON.

  - **Solution**: Your PHPSESSID is almost certainly expired or invalid. Follow the "Setting up PHPSESSID" steps to get a fresh one. Also, ensure your internet connection is stable.

- **HTTPError: 404 Client Error: Not Found**:

  - **Cause**: The specific API endpoint used by the script no longer exists or has changed for that content/user.

  - **Solution**: This is harder. You would need to manually inspect Pixiv's website using your browser's Developer Tools (Network tab, filter by XHR/Fetch) to find the new API endpoints Pixiv is using to load the data.

- **'list' object has no attribute 'keys'**:

  - **Cause**: The JSON structure of the API response has changed from a dictionary to a list.

  - **Solution**: The current script has logic to handle both dictionary and list structures for user's illusts and manga data. If this error persists, it implies a new structure that needs investigation.

- **Slow Downloads**:

   - **Solution**: Experiment with the MAX_DOWNLOAD_WORKERS variable in the script. Increasing it might help, but setting it too high could lead to rate limiting or overwhelming your network connection.

# License
This project is open-source and available under the MIT License.
