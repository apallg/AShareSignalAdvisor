<template>
  <div class="card" v-if="rows.length">
    <div class="card-title" v-if="title">{{ title }}<span v-if="count != null"> ({{ count }})</span></div>
    <table>
      <thead>
        <tr>
          <th v-for="col in columns" :key="col.key" :style="col.width ? { width: col.width } : {}">
            {{ col.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in rows" :key="rowKey ? row[rowKey] : i">
          <td v-for="col in columns" :key="col.key" :class="col.tdClass ? col.tdClass(row) : ''" :style="col.tdStyle ? col.tdStyle(row) : {}">
            <slot :name="'cell-' + col.key" :row="row" :value="row[col.key]">
              {{ col.format ? col.format(row[col.key], row) : row[col.key] ?? '--' }}
            </slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <div v-else class="card empty">{{ emptyText }}</div>
</template>
<script setup>
defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
  title: { type: String, default: '' },
  count: { default: null },
  emptyText: { type: String, default: '暂无数据' },
  rowKey: { type: String, default: '' },
})
</script>
