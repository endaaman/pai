<template>
<el-container>
  <el-header>
    <el-menu
      :default-active="activeIndex"
      class="el-menu-demo"
      mode="horizontal"
      background-color="#545c64"
      text-color="#fff"
      active-text-color="#ffd04b">
      <el-menu-item index="index"><nuxt-link to="/">Home</nuxt-link></el-menu-item>
      <el-menu-item index="results"><nuxt-link to="/results">Resusts</nuxt-link></el-menu-item>
    </el-menu>
  </el-header>

  <el-container>
    <el-main>
      <p>{{ activeIndex }}</p>
      <nuxt />
    </el-main>

  </el-container>
</el-container>

</template>

<script>

export default {
  data() {
    return {
      activeIndex: '',
    }
  },
  mounted() {
    this.activeIndex = this.$route.name;
  }
}
</script>

<style>
html {
  font-family: 'Source Sans Pro', -apple-system, BlinkMacSystemFont, 'Segoe UI',
    Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 16px;
  word-spacing: 1px;
  -ms-text-size-adjust: 100%;
  -webkit-text-size-adjust: 100%;
  -moz-osx-font-smoothing: grayscale;
  -webkit-font-smoothing: antialiased;
  box-sizing: border-box;
}

*,
*:before,
*:after {
  box-sizing: border-box;
  margin: 0;
}

.el-header {
  padding-left: 0;
  padding-right: 0;
}
</style>
