# WebMet25 - User Guide

## Quick Start

### 1. Select Radars 📡
1. Click "Show Radars ▼" to expand the radar list
2. Check one or more radars to display
3. Use "All" or "None" buttons for quick selection

### 2. Choose a Product 🌧️
1. Select a radar product from the dropdown (e.g., DBZH, VRAD)
2. Toggle between "Filtered" and "Unfiltered" products if needed
   - Filtered: Standard products
   - Unfiltered: Raw products (ending with 'o')

### 3. View Data 📊

#### Option A: Load Latest Data
- Click **"Load Latest"** to view the most recent radar scan
- This shows a single snapshot of the current conditions

#### Option B: Load Time Range
1. Click **"Select Time Range ▼"** to expand time controls
2. Choose a time window:
   - **Quick presets**: Click "Last 3h", "Last 6h", "Last 12h", or "Last 24h"
   - **Custom range**: Use the date/time pickers to select start and end times
3. Click **"Load Time Range"** to fetch historical data
4. Use animation controls to play through the time series

### 4. Animation Controls 🎬

#### Play/Pause
- Click the **▶** button to start animation
- Click **⏸** to pause
- Or press `Space` on your keyboard

#### Navigate Frames
- Click **◀** to go to previous frame (or press `←`)
- Click **▶** to go to next frame (or press `→`)
- Click **⟲** to jump to latest frame (or press `Home`)
- Drag the slider to jump to any frame

#### Adjust Speed
- Click the speed button to cycle through speeds: **0.5x** → **1x** → **2x**
- Or press `S` on your keyboard

### 5. Map Controls 🗺️

#### Basemap
Change the background map style:
- **Dark** - Dark theme (default)
- **Light** - Light theme
- **OpenStreetMap** - Standard OSM
- **Satellite** - Satellite imagery
- **Terrain** - Topographic map

#### Opacity
- Use the **Opacity** slider to adjust radar layer transparency
- Drag from 0% (invisible) to 100% (fully opaque)

### 6. Legend 🎨
- The color legend appears automatically when data is loaded
- Shows the color scale and values for the selected product
- Located in the bottom-left corner

## Keyboard Shortcuts ⌨️

| Key | Action |
|-----|--------|
| `Space` | Play/Pause animation |
| `←` | Previous frame |
| `→` | Next frame |
| `Home` | Go to latest frame |
| `L` | Load latest data |
| `S` | Cycle speed |

> **Note:** Shortcuts are disabled when typing in input fields

## Tips & Tricks 💡

### Multiple Radars
- Select multiple radars to compare coverage areas
- Each radar's data is displayed as a separate layer
- All selected radars update together during animation

### Time Ranges
- Longer time ranges may have fewer available frames
- Not all radars have data for all time periods
- The system will show which radars have data available

### Performance
- Loading many frames (50+) may take a few seconds
- Animation is smooth once frames are loaded
- Larger time ranges require more memory

### Mobile Usage
- All features work on tablets and phones
- Use landscape mode for best experience
- Touch the map to pan, pinch to zoom
- Control panel scrolls if needed

## Status Messages 📢

The status bar at the bottom of the control panel shows:
- **🔵 Blue (Loading)**: Data is being fetched
- **🟢 Green (Success)**: Operation completed successfully
- **🔴 Red (Error)**: Something went wrong

## Troubleshooting 🔧

### No data available
- Check if the selected radar(s) are operational
- Try a different product type
- Try a different time range
- Some radars may not have all products

### Animation not working
- Ensure you've loaded time range data (not just "Load Latest")
- Check that you have multiple frames loaded
- Look for the frame counter (e.g., "1 / 20")

### Map not showing radar data
- Check the opacity slider (should be > 0%)
- Verify the status message for errors
- Try refreshing the page

### Slow performance
- Reduce the time range to load fewer frames
- Close other browser tabs
- Try a faster internet connection
- Some products are larger and take longer to load

## Browser Requirements 🌐
- Modern browser with JavaScript enabled
- Recommended: Chrome, Firefox, Safari, or Edge (latest version)
- Stable internet connection for loading tiles

## Contact & Support 📧
For issues or questions, please refer to the repository documentation or create an issue on GitHub.

---

**Enjoy exploring radar data! 🌩️🌧️**
