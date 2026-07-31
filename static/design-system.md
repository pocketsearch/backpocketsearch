# Design System Document

## Spacing System
To create a consistent layout throughout the application, we will use an 8px grid system for all spacing:

- `--space-1: 8px;`
- `--space-2: 16px;`
- `--space-3: 24px;`
- `--space-4: 32px;`
- `--space-5: 40px;`
- `--space-6: 48px;`
- `--space-8: 64px;`
- `--space-12: 80px;`

---

## Typography
Establishing a clear typographic hierarchy will ensure consistency and readability. Here’s the proposed typography scale:

- **Headings**:  
  - **H1**: `font-size: 36px; font-weight: 600;`  
  - **H2**: `font-size: 24px; font-weight: 600;`  
  - **H3**: `font-size: 20px; font-weight: 600;`

- **Body Text**:
  - `font-size: 16px; font-weight: 400;`

- **Meta Info**:
  - `font-size: 14px; color: var(--ink-muted);`

---

## Color Palette
A unified color palette will help maintain a consistent aesthetic across the application:

- **Background**: `#FAFAFA`  
- **Surface**: `#FFFFFF`  
- **Border**: `#E5E7EB`  
- **Primary Accent**: `#6D5EFC`  
- **Neutral**:  
  - **Primary Text**: `#111111`  
  - **Secondary Text**: `#6B7280`

---

## Border Radius
To maintain a modern aesthetic while ensuring consistency, the following border radius will be used:

- Standard components: `6px`  
- Special cases (i.e., cards): `14-18px`

---

## Shadow Guidelines
Shadows will be used sparingly to enhance the visual hierarchy without overwhelming the design:

- Light shadow for elevated surfaces: `0 1px 4px rgba(0, 0, 0, 0.1)`
- Strong shadow for focal points: `0 2px 8px rgba(0, 0, 0, 0.2)`

---

## Component Styles
### Results Cards
- Background: `--surface`
- Border: `1px solid var(--border)`
- Border Radius: `14-18px`
- Padding: `var(--space-5)`

### Buttons
- Standard button styling with:
  - Background: `var(--primary)`/`transparent` for secondary
  - Border Radius: `6px`

### Navigation & Modals
- Consistent layouts using defined spacing and color tokens.

---

## Conclusion
This design system will serve as the foundation for creating a cohesive and polished user interface across the application, with a focus on whitespace, typography, and a unified aesthetic.