<template>
  <div class="layout">
    <aside class="rail">
      <div class="brand">闸序 Batchgate</div>
      <router-link to="/">总览</router-link>
      <router-link to="/jobs">作业</router-link>
      <router-link to="/orchestrate">编排台</router-link>
      <router-link to="/attempts">尝试记录</router-link>
      <router-link to="/watermarks">产出水位</router-link>
      <router-link to="/settings">设置</router-link>
    </aside>
    <main><router-view /></main>
  </div>
</template>
