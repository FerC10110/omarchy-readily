import QtQuick

// Temporary (Task 11): the panel calls reset() before showing it. Replaced in Task 13.
Item {
  id: view
  property var host: null
  readonly property Item focusItem: view
  implicitHeight: 0

  function reset(initialTags, initialSection) {
  }
}
