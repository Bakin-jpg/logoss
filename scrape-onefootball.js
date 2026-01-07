const axios = require('axios');
const cheerio = require('cheerio');
const fs = require('fs');
const path = require('path');
const { createCanvas, loadImage, registerFont } = require('canvas');

// Konfigurasi
const OUTPUT_DIR = './hasil_logo';
const THEME = 2;
const BACKGROUNDS = {
  1: 'https://images.unsplash.com/photo-1531685250784-7569952593d2?q=80&w=800&h=450&fit=crop',
  2: 'https://images.unsplash.com/photo-1518605348400-43ded97c9c6c?q=80&w=800&h=450&fit=crop',
  3: 'https://images.unsplash.com/photo-1605218427306-022ba6c1bc8f?q=80&w=800&h=450&fit=crop'
};

// Pastikan folder output ada
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// Download file helper
async function downloadFile(url, filePath) {
  const writer = fs.createWriteStream(filePath);
  const response = await axios({
    url,
    method: 'GET',
    responseType: 'stream'
  });
  
  response.data.pipe(writer);
  
  return new Promise((resolve, reject) => {
    writer.on('finish', resolve);
    writer.on('error', reject);
  });
}

// Main scraping function
async function scrapeOneFootball() {
  console.log('🚀 Mulai scraping OneFootball...');
  
  try {
    const response = await axios.get('https://onefootball.com/id/pertandingan', {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0'
      }
    });
    
    const $ = cheerio.load(response.data);
    const matches = [];
    
    // Cari semua section liga
    $('div[class*="xpaLayoutContainerFullWidth--matchCardsList"]').each((i, section) => {
      const league = $(section).find('h2[class*="Title_leftAlign"]').text().trim() || 'Liga';
      
      // Cari semua pertandingan dalam section
      $(section).find('a[class*="MatchCard_matchCard"]').each((j, matchCard) => {
        const homeTeam = $(matchCard).find('span[class*="__name__"]:first').text().trim();
        const awayTeam = $(matchCard).find('span[class*="__name__"]:last').text().trim();
        
        const homeImg = $(matchCard).find('img:first');
        const awayImg = $(matchCard).find('img:last');
        
        const homeLogo = homeImg.length ? homeImg.attr('src') : '';
        const awayLogo = awayImg.length ? awayImg.attr('src') : '';
        
        // Ambil waktu/status
        let timeStatus = '';
        const timeElem = $(matchCard).find('time').first();
        const statusElem = $(matchCard).find('span[class*="__infoMessage__"]').first();
        
        if (statusElem.length) {
          timeStatus = statusElem.text().trim();
        } else if (timeElem.length) {
          timeStatus = timeElem.text().trim();
        }
        
        // Skip jika ada skor (hanya mau yang "VS")
        const hasScore = $(matchCard).find('span[class*="__score__"]').length > 0;
        
        if (homeTeam && awayTeam && !hasScore) {
          matches.push({
            league,
            home: homeTeam,
            away: awayTeam,
            homeLogo: homeLogo ? decodeURIComponent(homeLogo.split('image=')[1] || homeLogo) : '',
            awayLogo: awayLogo ? decodeURIComponent(awayLogo.split('image=')[1] || awayLogo) : '',
            timeStatus: timeStatus || 'VS'
          });
        }
      });
    });
    
    console.log(`✅ Ditemukan ${matches.length} pertandingan`);
    
    // Download background
    const bgPath = './background.jpg';
    if (!fs.existsSync(bgPath)) {
      console.log('⬇️  Downloading background...');
      await downloadFile(BACKGROUNDS[THEME], bgPath);
    }
    
    // Download font
    const fontPath = './Roboto-Bold.ttf';
    if (!fs.existsSync(fontPath)) {
      console.log('⬇️  Downloading font...');
      await downloadFile(
        'https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf',
        fontPath
      );
    }
    
    // Register font
    registerFont(fontPath, { family: 'Roboto' });
    
    // Generate poster untuk setiap match
    console.log('🎨 Generating posters...');
    for (const match of matches.slice(0, 10)) { // Limit 10 biar ga kebanyakan
      await generatePoster(match, bgPath);
    }
    
    console.log('🎉 Selesai!');
    
  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  }
}

// Generate poster dengan Canvas
async function generatePoster(match, bgPath) {
  const WIDTH = 800;
  const HEIGHT = 450;
  
  const canvas = createCanvas(WIDTH, HEIGHT);
  const ctx = canvas.getContext('2d');
  
  try {
    // Load background
    const bg = await loadImage(bgPath);
    ctx.drawImage(bg, 0, 0, WIDTH, HEIGHT);
    
    // Dark overlay
    ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    
    // League pill
    ctx.fillStyle = 'rgba(30, 30, 40, 0.2)';
    const pillWidth = 280;
    const pillHeight = 44;
    const pillX = (WIDTH - pillWidth) / 2;
    const pillY = 30;
    
    // Round rect untuk pill
    ctx.beginPath();
    ctx.roundRect(pillX, pillY, pillWidth, pillHeight, 22);
    ctx.fill();
    
    // League text
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 15px Roboto';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(match.league.toUpperCase(), WIDTH / 2, pillY + pillHeight / 2);
    
    // Load logos
    const logoSize = 120;
    const logoY = 130;
    
    try {
      if (match.homeLogo) {
        const homeLogo = await loadImage(match.homeLogo);
        const homeX = (WIDTH * 0.25) - (logoSize / 2);
        ctx.drawImage(homeLogo, homeX, logoY, logoSize, logoSize);
      }
    } catch (e) {
      console.log(`⚠️  Gagal load logo home: ${match.home}`);
    }
    
    try {
      if (match.awayLogo) {
        const awayLogo = await loadImage(match.awayLogo);
        const awayX = (WIDTH * 0.75) - (logoSize / 2);
        ctx.drawImage(awayLogo, awayX, logoY, logoSize, logoSize);
      }
    } catch (e) {
      console.log(`⚠️  Gagal load logo away: ${match.away}`);
    }
    
    // VS Text (BESAR)
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 70px Roboto';
    ctx.fillText('VS', WIDTH / 2, 270);
    
    // Time/Status text
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 16px Roboto';
    ctx.fillText(match.timeStatus, WIDTH / 2, 310);
    
    // Team names
    ctx.font = 'bold 20px Roboto';
    
    // Home team
    const homeTextWidth = ctx.measureText(match.home).width;
    ctx.fillText(match.home, (WIDTH * 0.25), 380);
    
    // Home underline
    ctx.fillStyle = '#00eaff';
    ctx.fillRect((WIDTH * 0.25) - (homeTextWidth / 2), 390, homeTextWidth, 3);
    
    // Away team
    const awayTextWidth = ctx.measureText(match.away).width;
    ctx.fillStyle = '#FFFFFF';
    ctx.fillText(match.away, (WIDTH * 0.75), 380);
    
    // Away underline
    ctx.fillStyle = '#00eaff';
    ctx.fillRect((WIDTH * 0.75) - (awayTextWidth / 2), 390, awayTextWidth, 3);
    
    // Save image
    const fileName = match.home.replace(/[^a-z0-9]/gi, '_') + 
                    '_vs_' + 
                    match.away.replace(/[^a-z0-9]/gi, '_') + 
                    '.png';
    
    const filePath = path.join(OUTPUT_DIR, fileName);
    const buffer = canvas.toBuffer('image/png');
    fs.writeFileSync(filePath, buffer);
    
    console.log(`✅ Created: ${fileName}`);
    
  } catch (error) {
    console.error(`❌ Error creating poster for ${match.home} vs ${match.away}:`, error.message);
  }
}

// Polyfill untuk roundRect
CanvasRenderingContext2D.prototype.roundRect = function (x, y, w, h, r) {
  if (w < 2 * r) r = w / 2;
  if (h < 2 * r) r = h / 2;
  this.beginPath();
  this.moveTo(x + r, y);
  this.arcTo(x + w, y, x + w, y + h, r);
  this.arcTo(x + w, y + h, x, y + h, r);
  this.arcTo(x, y + h, x, y, r);
  this.arcTo(x, y, x + w, y, r);
  this.closePath();
  return this;
};

// Jalankan scraper
scrapeOneFootball();
