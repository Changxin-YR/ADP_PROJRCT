<script setup lang="ts">
// 统一线性图标集：2px 描边、圆角连接，替代大小粗细不一的 Unicode 字符图标（⌂◒✓▦⌾▤⇄◎◈⇅⚙ 等）
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })

const paths: Record<string, string> = {
  home: 'M4 11.5 12 4l8 7.5M6.5 10v9h11v-9M10 19v-5h4v5',
  bell: 'M6 10a6 6 0 0 1 12 0c0 4 .8 5.4 1.6 6.4.4.5.1 1.1-.5 1.1H4.9c-.6 0-.9-.6-.5-1.1C5.2 15.4 6 14 6 10ZM10 20.5a2.2 2.2 0 0 0 4 0',
  check: 'M4.5 12.5 9.5 17.5 19.5 6.5',
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  cycle: 'M12 4a8 8 0 0 1 7.4 4.9M20 12a8 8 0 0 1-7.4 7.1M4 12a8 8 0 0 1 2.3-5.6M9.5 20.5H5.5M18.5 3.5v4h-4',
  layers: 'M4 7.5 12 3.5l8 4-8 4-8-4ZM4 12.5 12 16.5l8-4M4 17 12 21l8-4',
  swap: 'M7 4v13M7 20l-3-3.5M7 20l3-3.5M17 20V7M17 4l-3 3.5M17 4l3 3.5',
  target: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16ZM12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7ZM12 11.4a.6.6 0 1 0 0 1.2.6.6 0 0 0 0-1.2Z',
  diamond: 'M12 3 21 12 12 21 3 12 12 3ZM8.5 8.5l7 7M15.5 8.5l-7 7',
  exchange: 'M16.5 3.5 21 8l-4.5 4.5M21 8H8M7.5 20.5 3 16l4.5-4.5M3 16h13',
  gear: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM12 2.8 13 5a7.2 7.2 0 0 1 2 1.2l2.4-.5 1.7 3-.5.6a7.2 7.2 0 0 1 0 2.4l.5.6-1.7 3-2.4-.5a7.2 7.2 0 0 1-2 1.2L12 21.2 11 19a7.2 7.2 0 0 1-2-1.2l-2.4.5-1.7-3 .5-.6a7.2 7.2 0 0 1 0-2.4l-.5-.6 1.7-3 2.4.5a7.2 7.2 0 0 1 2-1.2L12 2.8Z',
  search: 'M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM15.5 15.5 21 21',
  help: 'M9.3 9a2.8 2.8 0 1 1 3.8 2.6c-.7.3-1.1 1-1.1 1.8v.6M12 17.2v.1M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z',
  logout: 'M14 4h4.5a1.5 1.5 0 0 1 1.5 1.5v13A1.5 1.5 0 0 1 18.5 20H14M3.5 12h11M8 8l-4 4 4 4',
  download: 'M12 3v12M7.5 10.5 12 15l4.5-4.5M4 20h16',
  plus: 'M12 5v14M5 12h14',
  edit: 'M4 20h4l11-11-4-4L4 16v4ZM13.5 6.5l4 4',
  save: 'M5 4h12l2 2v14H5V4ZM8 4v6h8V4M8 20v-6h8v6',
  close: 'M6 6l12 12M18 6 6 18',
  menu: 'M4 6h16M4 12h16M4 18h16',
  calendar: 'M5 4h14a1 1 0 0 1 1 1v15H4V5a1 1 0 0 1 1-1ZM8 2v4M16 2v4M4 9h16',
  money: 'M4 6h16v12H4zM8 12h8M12 9v6M4 9a3 3 0 0 0 3-3M20 15a3 3 0 0 0-3 3',
  calculator: 'M6 3h12v18H6zM9 6h6v4H9zM9 14h.1M12 14h.1M15 14h.1M9 17h.1M12 17h.1M15 17h.1',
  info: 'M12 10v7M12 7h.1M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z',
  trend: 'M4 17l5-5 4 4 7-8M15 8h5v5',
  'chevron-down': 'M6 9l6 6 6-6',
}
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] ?? paths.help" /></svg>
</template>
