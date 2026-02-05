# Frontend - Radar Visualization Tool

Enhanced frontend for WebMet25 radar data visualization with modular architecture and advanced controls.

## Features

### 🎬 Animation Controls
- **Play/Pause**: Toggle animation playback
- **Speed Control**: Cycle through 0.5x, 1x, and 2x speeds
- **Frame Slider**: Manual navigation through time series
- **Auto-Loop**: Continuous playback through available frames
- **Frame Counter**: Shows current position (e.g., "5 / 20")

### 🎨 Color Legend
- **Dynamic Rendering**: Fetches colormap from API for each product
- **Vertical Color Bar**: Shows value ranges with colors
- **Value Labels**: Displays numeric values for each color step
- **Scrollable**: Handles long legends gracefully
- **Unit Display**: Shows measurement units when available

### 🔧 Map Controls
- **Radar Selection**: Choose from available radars
- **Product Selection**: Select radar product type (COLMAX, etc.)
- **Opacity Slider**: Adjust radar layer transparency (0-100%)
- **Time Display**: Shows observation time in local timezone
- **Navigation Buttons**: Previous/Next/Latest frame navigation

### 🎯 UI/UX
- **Dark Theme**: Professional look with #1a1a2e background
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Loading States**: Visual feedback during data fetching
- **Error Handling**: Clear error messages with graceful fallbacks

## Architecture

### Modular Structure

```
frontend/public/
├── index.html              # Main HTML page
├── css/
│   └── styles.css         # All styles (444 lines)
└── js/
    ├── api.js             # API client (70 lines)
    ├── map.js             # Map management (97 lines)
    ├── animation.js       # Animation controller (170 lines)
    ├── controls.js        # UI controls (148 lines)
    ├── legend.js          # Legend renderer (98 lines)
    └── app.js             # Main orchestrator (275 lines)
```

### Module Responsibilities

#### `api.js` - API Client
- Handles all backend communication
- Endpoints: radars, products, COGs, colormap, tiles
- Centralized error handling
- Configuration for API base URL

#### `map.js` - Map Manager
- Initializes Leaflet map
- Manages radar tile layers
- Controls layer opacity
- Handles map bounds and zoom

#### `animation.js` - Animation Controller
- Play/pause functionality
- Speed control (0.5x - 2x)
- Frame navigation
- Event-driven frame changes
- Loop control

#### `controls.js` - UI Controls
- Status messages
- Time display formatting
- Select population
- Button enable/disable
- Display updates

#### `legend.js` - Legend Renderer
- Renders colormap data
- Color box display
- Value labels
- Scrollable container
- Show/hide functionality

#### `app.js` - Main Application
- Initializes all modules
- Manages application state
- Coordinates module interactions
- Handles user events
- Error recovery

## API Integration

### Endpoints Used

```javascript
// Get available radars
GET /api/v1/radars
Response: { radars: [...] }

// Get available products
GET /api/v1/products
Response: { products: [...] }

// Get COG images
GET /api/v1/cogs?radar_code=AR5&product_key=COLMAX&page_size=30
Response: { cogs: [...], count, total, page, page_size }

// Get product colormap
GET /api/v1/products/{product_key}/colormap
Response: { product_key, entries: [...], min_value, max_value, unit }

// Get tile images
GET /api/v1/tiles/{cog_id}/{z}/{x}/{y}.png
Returns: PNG tile image
```

### Data Flow

1. **Initialization**
   - Load radars from API
   - Load products from API
   - Initialize map with dark basemap
   - Setup event listeners

2. **Selection Change**
   - User selects radar and product
   - Fetch COGs for selection (parallel)
   - Fetch colormap for product (parallel)
   - Initialize animation with frames
   - Render legend
   - Display first frame

3. **Animation**
   - Timer triggers frame changes
   - Update map layer with new COG
   - Update time display
   - Update frame counter
   - Loop when reaching end

4. **User Interactions**
   - Previous/Next: Manual frame navigation
   - Play/Pause: Toggle animation
   - Speed: Cycle through speeds
   - Slider: Jump to specific frame
   - Opacity: Adjust layer transparency

## Development

### Prerequisites

- Modern browser with ES6 module support
- Leaflet 1.9.4 (loaded from CDN)
- Backend API running on port 8000

### Local Development

```bash
# Serve with Python HTTP server
cd frontend/public
python3 -m http.server 8080

# Or use Node.js http-server
npx http-server -p 8080

# Access at http://localhost:8080
```

### Production Deployment

The frontend is served via Nginx with:
- Static file serving
- API proxy to backend
- CORS headers
- Gzip compression

See `frontend/nginx.conf` for configuration.

## Browser Support

- Chrome/Edge 88+
- Firefox 78+
- Safari 14+
- Mobile browsers with ES6 support

## Customization

### Changing Colors

Edit `css/styles.css`:
```css
/* Primary color */
#4fc3f7 -> your color

/* Background */
#1a1a2e -> your background

/* Accent colors */
#66bb6a (success), #ef5350 (error), #ffa726 (loading)
```

### Adding New Controls

1. Add HTML element in `index.html`
2. Add styles in `css/styles.css`
3. Create handler in `controls.js`
4. Wire up event in `app.js`

### Modifying Animation

Edit `animation.js`:
```javascript
// Change default speed
this.speed = 1.5; // 1.5x

// Change interval
const intervalMs = 800; // 800ms per frame

// Change speed options
const speeds = [0.5, 1.0, 1.5, 2.0, 3.0];
```

## Troubleshooting

### Map Not Loading
- Check browser console for errors
- Verify Leaflet CDN is accessible
- Check API connectivity

### No Data Showing
- Verify API is running (http://localhost:8000/api/v1/radars)
- Check if COG data exists in database
- Look for errors in browser console

### Animation Not Working
- Check if multiple frames are available
- Verify COG images are accessible
- Look for JavaScript errors

### Opacity Not Changing
- Ensure radar layer is loaded
- Check if map is initialized
- Verify slider value is updating

## Performance Tips

1. **Preloading**: Consider preloading next frame for smoother animation
2. **Caching**: Browser caches tile images automatically
3. **Limits**: Default COG fetch limit is 30 frames (adjustable)
4. **Network**: Animation works best with stable connection

## Future Enhancements

Potential additions inspired by reference implementation:
- [ ] Base map selector (multiple basemap options)
- [ ] Multiple radar overlays
- [ ] Drawing tools for analysis
- [ ] Export functionality
- [ ] Time range picker
- [ ] Favorite locations
- [ ] Measurement tools
- [ ] Statistics overlay

## Credits

Inspired by:
- [webmet.ohmc.ar](https://webmet.ohmc.ar/)
- [IgnaCat/radar-visualization-tool](https://github.com/IgnaCat/radar-visualization-tool)

Built with:
- [Leaflet](https://leafletjs.com/)
- [CartoDB Basemaps](https://carto.com/basemaps/)
