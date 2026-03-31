const form = document.getElementById("scrape-form");
const urlInput = document.getElementById("url-input");
const submitBtn = document.getElementById("submit-btn");
const statusDiv = document.getElementById("status");
const errorDiv = document.getElementById("error");

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const url = urlInput.value.trim();
    if (!url) return;

    // Reset UI
    statusDiv.classList.remove("hidden");
    errorDiv.classList.add("hidden");
    statusDiv.textContent = "Scraping menu... this may take 15-30 seconds.";
    submitBtn.disabled = true;

    try {
        const resp = await fetch("/api/scrape", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
        });

        if (!resp.ok) {
            const data = await resp.json();
            throw new Error(data.detail || `Server error ${resp.status}`);
        }

        // Download the file
        const blob = await resp.blob();
        const filename =
            resp.headers
                .get("content-disposition")
                ?.match(/filename="?([^"]+)"?/)?.[1] || "doordash-menu.xlsx";

        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();

        statusDiv.textContent = "Done! Your file should be downloading.";
    } catch (err) {
        statusDiv.classList.add("hidden");
        errorDiv.classList.remove("hidden");
        errorDiv.textContent = err.message;
    } finally {
        submitBtn.disabled = false;
    }
});
