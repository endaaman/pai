<template>
  <div>
    <el-table
      :data="results"
      style="width: 100%">
      <el-table-column prop="name" label="ID" width="180" />
      <el-table-column prop="mode" label="Mode" width="180" />

      <el-table-column
        prop="original"
        label="Original">
        <template slot-scope="scope">
          <img :src="scope.row.original" width=100/>
        </el-popover>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import { mapState, mapGetters } from 'vuex'

export default {
  async fetch({ store }) {
    await store.dispatch('result/getResults')
  },
  computed: {
    ...mapState('result', ['results']),
  },
}
</script>

<style>
</style>
