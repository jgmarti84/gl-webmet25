## Context
You are helping to enhance a radar visualization web application. The project structure and backend are complete. The frontend needs enhancement to match the functionality of https://webmet.ohmc.ar/ and should leverage code from https://github.com/IgnaCat/radar-visualization-tool.

## Your Tasks
### Task 1: Analyze the Reference Repository
Please analyze https://github.com/IgnaCat/radar-visualization-tool and identify:
1. File structure - How is the frontend organized?
2. Map implementation - How do they handle Leaflet map and radar layers?
3. Animation system - How is the time-based animation implemented?
4. UI components - What controls and widgets do they use?
5. API integration - How do they fetch and display radar data?
6. Colormap/Legend - How do they render the color scale?

### Task 2: Enhance the Frontend
Based on the reference repo, enhance our frontend/public/ files:

#### 2.1 Update index.html
* Add animation controls (play/pause/speed)
* Add legend container
* Add opacity slider
* Improve layout similar to webmet.ohmc.ar
#### 2.2 Update css/styles.css
* Style animation controls
* Style legend
* Add responsive design
* Match the dark theme aesthetic
#### 2.3 Update or refactor js/app.js
Consider splitting into modules if the reference repo does:

* js/api.js - API client
* js/map.js - Map management
* js/animation.js - Animation logic
* js/controls.js - UI controls
* js/legend.js - Legend rendering
* js/app.js - Main application

### Task 3: Specific Features to Implement
#### Animation System
```javascript
// Required functionality:
// - Play/pause toggle
// - Speed control (0.5x, 1x, 2x)
// - Loop through available timestamps
// - Smooth frame transitions
// - Preload next frame for smooth playback
```
#### Legend Component
```javascript
// Required functionality:
// - Fetch colormap from /api/v1/products/{key}/colormap
// - Render vertical or horizontal color bar
// - Show value labels
// - Update when product changes
```
#### Opacity Control
```javascript
// Required functionality:
// - Slider from 0 to 100%
// - Update radar layer opacity in real-time
// - Remember user preference
```
### Task 4: Code Quality Requirements
* Modular code - Separate concerns into files/modules
* Error handling - Graceful handling of API errors
* Loading states - Show loading indicators
* Comments - Document complex logic
* Responsive - Work on mobile devices
* Performance - Optimize for smooth animations
* Accessibility - Ensure controls are accessible