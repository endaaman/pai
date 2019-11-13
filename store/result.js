import axios from '~/plugins/axios'

export const state = () => ({
  results: [],
  isFetched: false,
})

export const mutations = {
  set(state, {items, }) {
    state.results = Array.from(items)
    state.isFetched = true
  },
}

export const actions = {
  async fetchResults({commit, getters, rootGetters, }) {
    const res = await axios.get('api/results')
    commit('set', {items: res.data})
  },
  async getResults({ state, dispatch }) {
    if (state.isFetched) {
      return
    }
    await dispatch('fetchResults')
  },
}

export const getters = {
}
