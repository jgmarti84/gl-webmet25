# Frontend Features - Radar Visualization WebMet25

## Overview
This document describes the radar-centric frontend features implemented for the WebMet25 radar visualization application. The implementation is inspired by https://webmet.ohmc.ar/ with improved UI/UX.

## New Features Implemented

### 1. Time Range Selection ⏰
Users can now select custom time windows for viewing historical radar data.

**Features:**
- **Date/Time Picker**: Select start and end dates/times using HTML5 datetime-local inputs
- **Quick Presets**: One-click buttons for common time ranges:
  - Last 3 hours
  - Last 6 hours
  - Last 12 hours
  - Last 24 hours
- **Collapsible Panel**: Time range controls are hidden by default to save screen space
- **Validation**: Automatic validation ensures start time is before end time

**Usage:**
1. Click "Select Time Range ▼" to expand the time range panel
2. Either:
   - Use preset buttons (Last 3h, 6h, 12h, 24h) for quick selection
   - Manually select start and end dates using the date pickers
3. Click "Load Time Range" to fetch and display radar data for the selected period
4. Use animation controls to play through the time series

### 2. Enhanced Animation System 🎬
The animation system has been improved to work with time-based data ranges.

**Features:**
- **Time Series Playback**: Animate through frames from the selected time range
- **Multi-Radar Support**: Can display and animate data from multiple radars simultaneously
- **Frame Counter**: Shows current frame position (e.g., "5 / 20")
- **Smooth Transitions**: Frames transition smoothly with no flickering
- **Speed Control**: Toggle between 0.5x, 1x, and 2x playback speeds

**Controls:**
- Play/Pause button (▶/⏸)
- Speed button (0.5x/1x/2x)
- Navigation buttons (◀, ⟲, ▶)
- Animation slider for scrubbing through frames

### 3. Keyboard Shortcuts ⌨️
Added keyboard shortcuts for efficient navigation and control.

**Shortcuts:**
- `Space` - Play/Pause animation
- `←` `→` - Navigate previous/next frame
- `Home` - Jump to latest frame
- `L` - Load latest data
- `S` - Cycle animation speed

**Note:** Shortcuts are disabled when typing in input fields.

### 4. Modern UI/UX Improvements ✨

**Visual Enhancements:**
- **Backdrop Blur**: Control panel has a modern glass-morphism effect
- **Smooth Transitions**: All interactive elements have smooth hover/active states
- **Button Feedback**: Buttons provide visual feedback with transform and shadow effects
- **Custom Scrollbars**: Styled scrollbars matching the dark theme
- **Color-Coded Status**: Status messages use colors (blue=loading, green=success, red=error)
- **Responsive Design**: Optimized for desktop, tablet, and mobile devices

**Interaction Improvements:**
- **Collapsible Sections**: Radar list and time range controls can be collapsed to save space
- **Hover Effects**: All interactive elements respond to hover with visual feedback
- **Loading States**: Clear loading indicators during data fetch operations
- **Error Handling**: Informative error messages when data is unavailable

### 5. Multi-Radar Support 📡
The application now fully supports multiple radars simultaneously.

**Features:**
- **Checkbox Selection**: Select one or more radars from the list
- **Bulk Actions**: "All" and "None" buttons to quickly select/deselect radars
- **Individual Display**: Each radar's data is displayed as a separate layer on the map
- **Automatic Bounds**: Map automatically zooms to show the selected radar coverage
- **Status Messages**: Clear feedback about which radars have data available

### 6. Improved Product Filtering 🔍
Enhanced product selection with filtering options.

**Features:**
- **Filtered/Unfiltered Toggle**: Switch between filtered and unfiltered products
  - Filtered products: Standard radar products
  - Unfiltered products: Products ending with 'o' (e.g., RHOHVo, COLMAXo)
- **Filter Button**: Visual indicator showing current filter state
- **Persistent Selection**: Maintains product selection when toggling filters (if available)

## API Integration

### New API Methods

#### `getCogsForTimeRange(radarCodes, productKey, startTime, endTime, limit)`
Fetches COG (Cloud Optimized GeoTIFF) files for multiple radars within a time range.

**Parameters:**
- `radarCodes` (Array): List of radar codes (e.g., ['rma1', 'rma3'])
- `productKey` (String): Product identifier (e.g., 'DBZH', 'VRAD')
- `startTime` (Date): Start of time range
- `endTime` (Date): End of time range
- `limit` (Number): Maximum number of COGs to fetch (default: 100)

**Returns:**
Array of COG objects sorted by observation_time (newest first)

**Example:**
```javascript
const cogs = await api.getCogsForTimeRange(
    ['rma1', 'rma3'], 
    'DBZH',
    new Date('2024-01-01T00:00:00Z'),
    new Date('2024-01-01T06:00:00Z'),
    50
);
```

## Architecture

### Modular Design
The frontend is organized into focused modules:

- **app.js** - Main application logic and state management
- **api.js** - Backend communication and data fetching
- **map.js** - Leaflet map management and radar layer display
- **animation.js** - Animation controller for frame playback
- **controls.js** - UI control handlers and state updates
- **legend.js** - Color legend rendering from colormaps

### State Management
Application state is centralized in the `state` object:
```javascript
{
    radars: [],              // Available radars
    products: [],            // Available products
    selectedRadars: [],      // Currently selected radar codes
    selectedProduct: null,   // Currently selected product
    cogs: [],               // Loaded COG frames
    mapManager: null,       // Map controller instance
    animator: null,         // Animation controller instance
    ui: null,               // UI controls instance
    legend: null            // Legend renderer instance
}
```

## Browser Compatibility
- Modern browsers with ES6 module support
- Chrome/Edge 89+
- Firefox 89+
- Safari 15+
- Mobile browsers (iOS Safari, Chrome Mobile)

## Responsive Breakpoints
- **Desktop**: > 768px - Full features
- **Tablet**: 481px - 768px - Optimized layout
- **Mobile**: ≤ 480px - Compact layout with scrollable controls

## Performance Considerations
- **COG Tiling**: Uses tiled COG format for efficient map rendering
- **Lazy Loading**: Radar layers loaded on-demand
- **Frame Preloading**: Animation frames loaded in advance for smooth playback
- **Debounced Updates**: UI updates are optimized to prevent excessive redraws

## Accessibility
- Keyboard navigation support for all interactive elements
- ARIA labels on buttons and controls
- Sufficient color contrast for readability
- Focus indicators on interactive elements

## Future Enhancements
Potential improvements for future versions:
- Date range picker with calendar UI
- Export animation as GIF/video
- Bookmark/save favorite time ranges
- Multiple time range comparison
- Touch gestures for mobile (pinch/swipe)
- Dark/light theme toggle
- Advanced product filtering by parameters

## Technical Stack
- **Map Library**: Leaflet 1.9.4
- **Tile Format**: COG (Cloud Optimized GeoTIFF)
- **API**: FastAPI backend with PostgreSQL/PostGIS
- **Styling**: Custom CSS with modern effects
- **Architecture**: Modular ES6 JavaScript

## Credits
Inspired by the original webmet.ohmc.ar implementation with significant enhancements and modernization.
