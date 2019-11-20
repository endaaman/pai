<template>
  <v-simple-table>
    <template v-slot:default>
      <thead>
        <tr>
          <th class="text-left">Name</th>
          <th class="text-left">Mode</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in results" :key="r.name">
          <td>{{ r.name }}</td>
          <td>{{ r.mode }}</td>
        </tr>
      </tbody>
    </template>
  </v-simple-table>
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
  mounted() {
    console.log(this.results)
  },

}
</script>

<style>
</style>
