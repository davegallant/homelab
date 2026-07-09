# How to Migrate YouTube Subscriptions to Invidious

This guide explains how to extract your YouTube subscriptions using a browser console script and import them into Invidious without needing to use Google Takeout.

## Part 1: Extract Subscriptions from YouTube

1. Go to your **[YouTube Subscriptions Manager](https://www.youtube.com/feed/channels)**.
2. **Scroll down to the very bottom** of the page so all your subscribed channels load into view.
3. Press **F12** (or right-click and choose "Inspect") and open the **Console** tab.
4. **Copy the code block below**:

```javascript
// Extract channel elements from the page
let channels = document.querySelectorAll('ytd-channel-renderer');
let csvContent = "Channel Id,Channel Url,Channel Title\n";

channels.forEach(channel => {
    let titleElement = channel.querySelector('#channel-title');
    let linkElement = channel.querySelector('#main-link');
    
    if (titleElement && linkElement) {
        // Clean up the title and escape quotes for CSV format
        let title = titleElement.innerText.trim().replace(/"/g, '""');
        let url = linkElement.href;
        
        // Find the actual UC... channel ID (Invidious requires this, not the @handle)
        let id = "";
        
        // Check internal YouTube element data
        if (channel.data && channel.data.channelId) {
            id = channel.data.channelId;
        } else if (channel.__data && channel.__data.data && channel.__data.data.channelId) {
            id = channel.__data.data.channelId;
        } 

        // Check for any hidden links
        if (!id) {
            let ucLink = channel.querySelector('a[href^="/channel/UC"]');
            if (ucLink) id = ucLink.href.split('/channel/')[1];
        }
        
        // Fallback to URL handle if absolutely necessary
        if (!id) id = url.split('/').pop(); 
        
        // Invidious expects the URL to be the /channel/UC... format too
        let finalUrl = id.startsWith('UC') ? `https://www.youtube.com/channel/${id}` : url;
        
        csvContent += `"${id}","${finalUrl}","${title}"\n`;
    }
});

// Create a downloadable CSV file automatically
let blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
let link = document.createElement("a");
let url = URL.createObjectURL(blob);
link.setAttribute("href", url);
link.setAttribute("download", "subscriptions.csv");
link.style.visibility = 'hidden';
document.body.appendChild(link);
link.click();
document.body.removeChild(link);
console.log(`Successfully exported ${channels.length} subscriptions!`);
```

5. Paste the code directly into the Console where the blinking cursor is, and press **Enter**. A file named `subscriptions.csv` will instantly download to your computer.

---

## Part 2: Import into Invidious

1. **Log in** to your preferred Invidious instance (e.g., `yewtu.be`, `invidious.nerdvpn.de`, etc.).
2. Go to the **Preferences** page (usually represented by a gear icon ⚙️ or a link in the top right/left menu).
3. Scroll all the way to the bottom of the Preferences page and click on the **Import/export data** link.
4. On the new page, look for the section titled **Import YouTube subscriptions**.
5. Click **Browse** (or "Choose File") and select the `subscriptions.csv` file you just downloaded.
6. Click the **Import** button right below it. 

*Note: Depending on how many channels you are subscribed to, it might take a few moments for them all to populate in your feed.*
