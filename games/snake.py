#!/usr/bin/env python3
"""贪吃蛇游戏 - 使用 Pygame 实现"""

import pygame
import random
import sys

# 初始化 Pygame
pygame.init()

# 游戏常量
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
GRID_SIZE = 20
GRID_WIDTH = WINDOW_WIDTH // GRID_SIZE
GRID_HEIGHT = WINDOW_HEIGHT // GRID_SIZE

# 颜色 (R, G, B)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
DARK_GREEN = (0, 200, 0)
RED = (255, 0, 0)
DARK_RED = (200, 0, 0)
BLUE = (0, 100, 255)
GRAY = (100, 100, 100)
LIGHT_GRAY = (200, 200, 200)

# 方向常量
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)


class Snake:
    """蛇类"""

    def __init__(self):
        # 初始蛇身：3节，水平放置
        start_x = GRID_WIDTH // 2
        start_y = GRID_HEIGHT // 2
        self.body = [
            (start_x, start_y),
            (start_x - 1, start_y),
            (start_x - 2, start_y),
        ]
        self.direction = RIGHT
        self.next_direction = RIGHT
        self.grow_flag = False

    def change_direction(self, new_dir):
        """改变方向（不允许直接掉头）"""
        # 不允许反向移动
        if (new_dir[0] * -1, new_dir[1] * -1) != self.direction:
            self.next_direction = new_dir

    def move(self):
        """移动蛇"""
        self.direction = self.next_direction
        head = self.body[0]
        new_head = (head[0] + self.direction[0], head[1] + self.direction[1])

        # 插入新头
        self.body.insert(0, new_head)

        # 如果没吃到食物，移除尾部
        if not self.grow_flag:
            self.body.pop()
        else:
            self.grow_flag = False

    def grow(self):
        """设置增长标记"""
        self.grow_flag = True

    def check_self_collision(self):
        """检查是否撞到自己（头碰到身体）"""
        return self.body[0] in self.body[1:]

    def check_wall_collision(self):
        """检查是否撞墙"""
        head = self.body[0]
        return (head[0] < 0 or head[0] >= GRID_WIDTH or
                head[1] < 0 or head[1] >= GRID_HEIGHT)

    def get_head(self):
        return self.body[0]

    def draw(self, surface):
        """绘制蛇"""
        for i, segment in enumerate(self.body):
            x = segment[0] * GRID_SIZE
            y = segment[1] * GRID_SIZE
            rect = pygame.Rect(x, y, GRID_SIZE, GRID_SIZE)

            # 蛇头用亮绿色，身体用深绿色
            if i == 0:
                pygame.draw.rect(surface, GREEN, rect)
                # 蛇头边框
                pygame.draw.rect(surface, DARK_GREEN, rect, 2)
                # 眼睛
                eye_size = 4
                if self.direction == RIGHT:
                    eye1 = (x + 14, y + 4)
                    eye2 = (x + 14, y + 12)
                elif self.direction == LEFT:
                    eye1 = (x + 2, y + 4)
                    eye2 = (x + 2, y + 12)
                elif self.direction == UP:
                    eye1 = (x + 4, y + 2)
                    eye2 = (x + 12, y + 2)
                else:  # DOWN
                    eye1 = (x + 4, y + 14)
                    eye2 = (x + 12, y + 14)
                pygame.draw.circle(surface, WHITE, eye1, eye_size)
                pygame.draw.circle(surface, WHITE, eye2, eye_size)
                pygame.draw.circle(surface, BLACK, eye1, 2)
                pygame.draw.circle(surface, BLACK, eye2, 2)
            else:
                pygame.draw.rect(surface, DARK_GREEN, rect)
                pygame.draw.rect(surface, GREEN, rect, 1)


class Food:
    """食物类"""

    def __init__(self, snake_body):
        self.position = self._random_position(snake_body)

    def _random_position(self, snake_body):
        """在蛇身不占用的位置随机生成食物"""
        while True:
            pos = (random.randint(0, GRID_WIDTH - 1),
                   random.randint(0, GRID_HEIGHT - 1))
            if pos not in snake_body:
                return pos

    def respawn(self, snake_body):
        """重新生成食物"""
        self.position = self._random_position(snake_body)

    def draw(self, surface):
        """绘制食物（红色苹果样式）"""
        x = self.position[0] * GRID_SIZE
        y = self.position[1] * GRID_SIZE
        center = (x + GRID_SIZE // 2, y + GRID_SIZE // 2)

        # 苹果主体
        pygame.draw.circle(surface, RED, center, GRID_SIZE // 2 - 2)
        pygame.draw.circle(surface, DARK_RED, center, GRID_SIZE // 2 - 4, 2)

        # 高光
        highlight = (x + 6, y + 6)
        pygame.draw.circle(surface, (255, 150, 150), highlight, 3)

        # 叶子
        leaf_points = [
            (x + 14, y + 2),
            (x + 18, y + 1),
            (x + 16, y + 5),
        ]
        pygame.draw.polygon(surface, GREEN, leaf_points)


class Game:
    """游戏主类"""

    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("贪吃蛇 🐍")
        self.clock = pygame.time.Clock()
        self.font_large = pygame.font.SysFont("simhei", 48, bold=True)
        self.font_medium = pygame.font.SysFont("simhei", 32)
        self.font_small = pygame.font.SysFont("simhei", 20)
        self.reset()

    def reset(self):
        """重置游戏"""
        self.snake = Snake()
        self.food = Food(self.snake.body)
        self.score = 0
        self.game_over = False
        self.paused = False
        self.speed = 10  # 初始速度（帧率）

    def handle_events(self):
        """处理输入事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if self.game_over:
                    if event.key == pygame.K_r:
                        self.reset()
                    elif event.key == pygame.K_q:
                        return False
                    continue

                if event.key == pygame.K_p:
                    self.paused = not self.paused
                    continue

                if self.paused:
                    continue

                # 方向控制
                if event.key == pygame.K_UP or event.key == pygame.K_w:
                    self.snake.change_direction(UP)
                elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                    self.snake.change_direction(DOWN)
                elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                    self.snake.change_direction(LEFT)
                elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                    self.snake.change_direction(RIGHT)

        return True

    def update(self):
        """更新游戏状态"""
        if self.game_over or self.paused:
            return

        self.snake.move()

        # 检查碰撞
        if self.snake.check_wall_collision() or self.snake.check_self_collision():
            self.game_over = True
            return

        # 检查是否吃到食物
        if self.snake.get_head() == self.food.position:
            self.snake.grow()
            self.score += 10
            self.food.respawn(self.snake.body)

            # 每得50分加速一次（最高20）
            self.speed = min(20, 10 + self.score // 50)

    def draw_grid(self):
        """绘制网格背景"""
        for x in range(0, WINDOW_WIDTH, GRID_SIZE):
            pygame.draw.line(self.screen, (30, 30, 30), (x, 0), (x, WINDOW_HEIGHT))
        for y in range(0, WINDOW_HEIGHT, GRID_SIZE):
            pygame.draw.line(self.screen, (30, 30, 30), (0, y), (WINDOW_WIDTH, y))

    def draw_score(self):
        """绘制得分"""
        score_text = self.font_medium.render(f"得分: {self.score}", True, WHITE)
        self.screen.blit(score_text, (10, 10))

        # 速度显示
        speed_text = self.font_small.render(f"速度: {self.speed}", True, LIGHT_GRAY)
        self.screen.blit(speed_text, (10, 50))

    def draw_game_over(self):
        """绘制游戏结束画面"""
        # 半透明遮罩
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        overlay.set_alpha(180)
        overlay.fill(BLACK)
        self.screen.blit(overlay, (0, 0))

        # 游戏结束文字
        title = self.font_large.render("游戏结束", True, RED)
        title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 60))
        self.screen.blit(title, title_rect)

        # 最终得分
        score_text = self.font_medium.render(f"最终得分: {self.score}", True, WHITE)
        score_rect = score_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
        self.screen.blit(score_text, score_rect)

        # 提示
        hint1 = self.font_small.render("按 R 重新开始", True, LIGHT_GRAY)
        hint1_rect = hint1.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 50))
        self.screen.blit(hint1, hint1_rect)

        hint2 = self.font_small.render("按 Q 退出", True, LIGHT_GRAY)
        hint2_rect = hint2.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 80))
        self.screen.blit(hint2, hint2_rect)

    def draw_pause(self):
        """绘制暂停提示"""
        pause_text = self.font_large.render("暂停", True, BLUE)
        pause_rect = pause_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
        self.screen.blit(pause_text, pause_rect)

        hint = self.font_small.render("按 P 继续", True, LIGHT_GRAY)
        hint_rect = hint.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 50))
        self.screen.blit(hint, hint_rect)

    def draw_start_hint(self):
        """绘制操作提示"""
        hints = [
            "方向键/WASD: 移动",
            "P: 暂停",
            "R: 重新开始",
        ]
        for i, hint in enumerate(hints):
            text = self.font_small.render(hint, True, GRAY)
            self.screen.blit(text, (WINDOW_WIDTH - 180, 10 + i * 25))

    def render(self):
        """渲染画面"""
        self.screen.fill(BLACK)
        self.draw_grid()

        if not self.game_over:
            self.food.draw(self.screen)
            self.snake.draw(self.screen)

        self.draw_score()
        self.draw_start_hint()

        if self.game_over:
            self.draw_game_over()
        elif self.paused:
            self.draw_pause()

        pygame.display.flip()

    def run(self):
        """游戏主循环"""
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.render()
            self.clock.tick(self.speed)

        pygame.quit()
        sys.exit()


def main():
    """入口函数"""
    print("🐍 贪吃蛇游戏启动中...")
    print("操作说明:")
    print("  方向键/WASD - 控制方向")
    print("  P - 暂停/继续")
    print("  R - 重新开始")
    print("  Q - 退出")
    print()

    game = Game()
    game.run()


if __name__ == "__main__":
    main()
