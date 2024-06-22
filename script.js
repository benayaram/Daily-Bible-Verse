// Function to save verse as image with template
function saveVerseImageWithTemplate(bookName, chapterNumber, verseNumber, verseText) {
    const templateImage = new Image();
    templateImage.onload = function() {
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');

        // Set canvas dimensions to match template image (or customize as needed)
        canvas.width = templateImage.width || 800; // Adjust width as needed
        canvas.height = templateImage.height || 600; // Adjust height as needed

        // Draw template image onto canvas (if provided)
        if (templateImage.src) {
            context.drawImage(templateImage, 0, 0, canvas.width, canvas.height);
        } else {
            // Alternatively, fill with a background color
            context.fillStyle = '#f0f0f0'; // Light gray background
            context.fillRect(0, 0, canvas.width, canvas.height);
        }

        // Load custom font
        const customFont = new FontFace('Suravaramfont', `url('./Suravaramfont.ttf')`);
        customFont.load().then(function(loadedFont) {
            document.fonts.add(loadedFont);
            // Apply custom font to context
            context.font = 'bold 36px Arial'; // Example: Use Suravaramfont as primary, fallback to Arial
            context.fillStyle = '#fff'; // White color for text
            context.textAlign = 'center'; // Center-align text

            // Display book name, chapter, and verse number
            const referenceText = `${bookName} ${chapterNumber}:${verseNumber}`;
            context.fillText(referenceText, canvas.width / 2, 100); // Adjust vertical position here

            // Set text style for verse text
            context.font = '40px Suravaramfont, Arial'; // Example: Use Suravaramfont as primary, fallback to Arial
            context.fillStyle = '#fff'; // White color for verse text
            context.textAlign = 'center'; // Center-align text

            // Break verse text into lines
            const lines = breakTextIntoLines(verseText, canvas.width - 100); // Adjust line width as needed

            // Calculate text positioning within canvas
            let textY = canvas.height / 2 - (lines.length / 2) * 40; // Center vertically

            // Draw each line of verse text with spacing
            lines.forEach(line => {
                context.fillText(line, canvas.width / 2, textY);
                textY += 50; // Adjust line spacing (increase or decrease as needed)
            });

            // Convert canvas to image data URL
            const dataURL = canvas.toDataURL(); // Default format is PNG

            // Create a link element to download the image
            const link = document.createElement('a');
            link.href = dataURL;
            link.download = 'daily_bible_verse.png'; // File name when downloaded

            // Simulate click to trigger download
            link.click();
        }).catch(function(error) {
            console.error('Failed to load font:', error);
        });
    };

    // Set template image source (replace 'path/to/template.png' with actual path)
    templateImage.src = './versebackground.png'; // Optional: Replace with actual path to template image
}

// Function to break text into lines based on width
function breakTextIntoLines(text, maxWidth) {
    const words = text.split(' ');
    let lines = [];
    let currentLine = words[0];
    const context = document.createElement('canvas').getContext('2d');
    context.font = '40px Suravaramfont, Arial'; // Match the verse text font size here

    for (let i = 1; i < words.length; i++) {
        const word = words[i];
        const width = context.measureText(currentLine + ' ' + word).width;
        if (width < maxWidth) {
            currentLine += ' ' + word;
        } else {
            lines.push(currentLine);
            currentLine = word;
        }
    }
    lines.push(currentLine);
    return lines;
}
// Initial load on page load
window.addEventListener('load', function() {
    fetchAndParseXML();
});

// Function to fetch and parse XML data asynchronously
async function fetchAndParseXML() {
    try {
        const response = await fetch('telugubible.xml'); // Replace with your XML file path
        const xmlText = await response.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, 'text/xml');

        const bibleContainer = document.getElementById('bibleContainer');
        const books = xmlDoc.getElementsByTagName('BIBLEBOOK');

        for (let i = 0; i < books.length; i++) {
            const book = books[i];
            const bookName = book.getAttribute('bname');

            // Create a card for the book
            const bookCard = createBookCard(bookName);
            bibleContainer.appendChild(bookCard);

            // Get verses for the current book
            const verses = book.getElementsByTagName('VERS');
            for (let j = 0; j < verses.length; j++) {
                const verse = verses[j];
                const chapterNumber = verse.parentNode.getAttribute('cnumber');
                const verseNumber = verse.getAttribute('vnumber');
                const verseText = verse.textContent.trim();

                // Create a card for each verse
                const verseCard = createVerseCard(bookName, chapterNumber, verseNumber, verseText);
                bookCard.appendChild(verseCard);
            }
        }
    } catch (error) {
        console.error('Error fetching or parsing XML:', error);
    }
}

// Function to create a card for the book
function createBookCard(bookName) {
    const bookCard = document.createElement('div');
    bookCard.classList.add('book-card');
    bookCard.innerHTML = `
        <div class="book-header">
            <h2>${bookName}</h2>
        </div>
        <div class="verse-list">
            <!-- Verses will be dynamically added here -->
        </div>
    `;
    return bookCard;
}

// Function to create a verse card
function createVerseCard(bookName, chapterNumber, verseNumber, verseText) {
    const verseCard = document.createElement('div');
    verseCard.classList.add('verse-card');
    verseCard.innerHTML = `
        <div class="verse-content">
            <div class="verse-header">
                <strong>${chapterNumber}:${verseNumber}</strong>
            </div>
            <div class="verse-text">
                <p>${verseText}</p>
            </div>
        </div>
    `;

    // Add event listener for Daily Bible Verse modal
    verseCard.addEventListener('click', function() {
        openDailyVerseModal(bookName, chapterNumber, verseNumber, verseText);
    });

    return verseCard;
}

// Function to open Daily Bible Verse modal
function openDailyVerseModal(bookName, chapterNumber, verseNumber, verseText) {
    const modal = document.getElementById('modal');
    const modalContent = modal.querySelector('.modal-content');

    // Update modal content with verse information
    const verseHeader = modalContent.querySelector('#verseHeader');
    const verseTextElement = modalContent.querySelector('#verseText');
    verseHeader.textContent = `${bookName} ${chapterNumber}:${verseNumber}`;
    verseTextElement.textContent = verseText;

    // Show modal
    modal.style.display = 'block';

    // Close modal when the close button or outside modal area is clicked
    const closeModal = modal.querySelector('.close');
    closeModal.addEventListener('click', function() {
        modal.style.display = 'none';
    });

    window.addEventListener('click', function(event) {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    });

    // Add event listeners for Copy to Clipboard and Save Image buttons
    const copyToClipboardButton = modalContent.querySelector('#copyToClipboard');
    const saveImageButton = modalContent.querySelector('#saveImage');

    copyToClipboardButton.addEventListener('click', function() {
        navigator.clipboard.writeText(verseText)
            .then(() => alert('Verse copied to clipboard!'))
            .catch(err => console.error('Failed to copy verse:', err));
    });

    saveImageButton.addEventListener('click', function() {
        saveVerseImageWithTemplate(bookName, chapterNumber, verseNumber, verseText);
    });
}

