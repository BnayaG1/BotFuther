const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// מגיש את כל הקבצים הסטטיים (index.html, styles.css, script.js)
app.use(express.static(path.join(__dirname)));

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Landing page server running on port ${PORT}`);
});
