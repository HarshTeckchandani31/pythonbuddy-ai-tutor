export type LearnerLevel = "beginner" | "intermediate" | "advanced";
export type LearningMode = "learn" | "practice" | "quiz" | "doubt";

export interface LearnerProfile {
  name: string;
  level: LearnerLevel;
  difficulty: LearnerLevel;
  topic: string;
}

export interface Progress {
  attempted: number;
  correct: number;
  accuracy_percent: number;
  strengths: string[];
  needs_practice: string[];
}

export interface LearnerSession {
  session_id: string;
  profile: LearnerProfile;
  progress: Progress;
}

export interface LessonContent {
  explanation: string;
  example: string;
  check_question: string;
}

export interface DoubtContent {
  answer: string;
  follow_up_question: string;
}

export interface TutorQuestion {
  question_id: string;
  question: string;
  skill: string;
}

export interface PracticeAnswer {
  correct: boolean;
  feedback: string;
  correct_answer: string;
  explanation: string;
  hint: string;
  progress: Progress;
}

export interface QuizAnswer {
  question_id: string;
  correct: boolean;
  feedback: string;
  correct_answer: string;
  explanation: string;
  score: number;
  answered: number;
  complete: boolean;
  next_question: TutorQuestion | null;
}

export interface SessionSummary {
  progress: Progress;
  recommendation: string;
  next_topic: string;
}
