# FIMpad Known Bugs and Quirks

## Unwanted scroll reposition when toggling line numbers on or off

When you press Ctrl+Alt+N to toggle line numbering, after the toggle, your view will scroll to be vertically centered with the carat. This can be annoying when you were scrolling down far past the carat and want to toggle line numbers, as you lose the view of what you were looking at. But so far I am unable to find a way to prevent this with the Tkinter widget that FIMpad uses. For now, the only thing you can do to preserve your scroll position when toggling line numbers is to click the carat in place on the line that you are looking at before you toggle line numbering on or off.


