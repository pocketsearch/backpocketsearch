# Minimalist Homepage Redesign - Complete

## Changes Made to pocketSearch

### Updated Files

**templates/index.html** - Complete redesign
- ✅ Removed navbar (hidden with `display: none`)
- ✅ Removed footer (hidden with `display: none`) 
- ✅ Removed logo and branding
- ✅ Removed mode hints and help text
- ✅ Removed tools button and popover
- ✅ Removed mode selector buttons (auto/domain/person/code)
- ✅ Simplified search box to minimal design
- ✅ Black background (#000000)
- ✅ Centered search bar in full viewport
- ✅ Thin underline only (1px solid #333333)
- ✅ White text on black (#ffffff)
- ✅ Monospace font (IBM Plex Mono)
- ✅ Minimal placeholder "_"
- ✅ Removed all visual noise

**templates/base.html** - Theme forcing
- ✅ Added dark theme class to `<html>` on index page
- ✅ Updated script to force dark theme on "/"
- ✅ Ensures consistent dark appearance

### Design Philosophy

The new homepage is:
- **Brutalist**: Minimal decoration, pure function
- **Minimalist**: Only search input, nothing else visible
- **Dark**: Black (#000000) background by default
- **Clean**: Simple border-bottom for visual clarity
- **Distraction-free**: All UI elements hidden except search
- **Fast**: Instant visual load, minimal DOM

### Visual Spec

```
Full black screen (100vh x 100vw)
├─ Center vertically and horizontally
└─ Search input
   ├─ Width: min(600px, 100vw - 40px)
   ├─ Height: 42px
   ├─ Border: none (bottom only: 1px #333333)
   ├─ Background: #000000
   ├─ Text color: #ffffff
   ├─ Font: IBM Plex Mono, 14px
   ├─ Placeholder: "_"
   └─ Letter-spacing: 0.5px
```

### Interactions Preserved

✅ Auto-focus on page load  
✅ Form submission on Enter  
✅ Ctrl+K focus shortcut  
✅ Proper form method (POST to /go)  
✅ Hidden "auto" mode value  

### Pages Not Affected

- ✅ Search results page
- ✅ Workspace
- ✅ Saved items
- ✅ History
- ✅ About
- ✅ All other routes

Only the home page (/) is affected. When users navigate away, normal navbar/footer return.

### Browser Compatibility

✅ Modern browsers (Chrome, Firefox, Safari, Edge)  
✅ Mobile responsive (adapts to small screens)  
✅ Monospace font fallbacks included  
✅ No JavaScript required for styling  

### Accessibility

✅ Proper ARIA labels maintained  
✅ Form semantics intact  
✅ Keyboard navigation working  
✅ High contrast (white on black)  
✅ Focus states visible  

## Before vs After

### Before
- Large navbar at top (hidden on home via overflow)
- Logo with label ("KitPocket Recon")
- Large search box (48px height)
- 4 mode selector buttons below
- Mode hint text
- Tools button with popover
- White/light background
- Visual clutter

### After
- No navbar (display: none)
- No logo
- Thin search box (42px height)
- No mode buttons
- No help text
- No tools menu
- Black background
- Pure minimalism

## Testing

✅ Template renders without errors  
✅ Dark theme applied automatically  
✅ Search bar visible and centered  
✅ Form submits correctly  
✅ Other pages unaffected  
✅ All CSS rules working  

## Deployment

Just git commit and push:
```bash
git add templates/index.html templates/base.html
git commit -m "Redesign homepage: minimalist brutalist dark theme"
```

No additional configuration needed. Changes take effect immediately.
