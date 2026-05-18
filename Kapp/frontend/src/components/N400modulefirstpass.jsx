import React, { useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CheckCircle2, XCircle, RotateCcw, Search, Volume2, UserRound, BookOpen, Plane, Home, Briefcase, Heart, Users } from "lucide-react";

const selfTest1 = [
  {
    id: 1,
    passage: "The employee’s name is Mr. John David Fenton.",
    question: "What is his first name?",
    options: ["Mr.", "John", "David"],
    answer: "John",
    topic: "Name",
  },
  {
    id: 2,
    passage: "The employee’s name is Mr. John David Fenton.",
    question: "What is his family name?",
    options: ["Mr.", "Fenton", "John"],
    answer: "Fenton",
    topic: "Name",
  },
  {
    id: 3,
    passage: "The employee’s name is Mr. John David Fenton.",
    question: "What is his middle name?",
    options: ["Mr.", "John", "David"],
    answer: "David",
    topic: "Name",
  },
  {
    id: 4,
    passage: "Bill was born in Australia and now lives in Chicago, Illinois. His address is 220 Cedar Street, Apt. B1, Chicago, Illinois 60603.",
    question: "What is Bill’s country of birth?",
    options: ["Australia", "Illinois", "United States"],
    answer: "Australia",
    topic: "Country of birth",
  },
  {
    id: 5,
    passage: "Bill was born in Australia and now lives in Chicago, Illinois. His address is 220 Cedar Street, Apt. B1, Chicago, Illinois 60603.",
    question: "Where does Bill currently live?",
    options: ["Texas", "Australia", "Chicago"],
    answer: "Chicago",
    topic: "Current address",
  },
  {
    id: 6,
    passage: "Bill was born in Australia and now lives in Chicago, Illinois. His address is 220 Cedar Street, Apt. B1, Chicago, Illinois 60603.",
    question: "What is Bill’s apartment number?",
    options: ["B1", "60603", "220"],
    answer: "B1",
    topic: "Current address",
  },
  {
    id: 7,
    passage: "Bill was born in Australia and now lives in Chicago, Illinois. His address is 220 Cedar Street, Apt. B1, Chicago, Illinois 60603.",
    question: "What is Bill’s zip code?",
    options: ["220", "60603", "B1"],
    answer: "60603",
    topic: "Current address",
  },
  {
    id: 8,
    passage: "Tom works as a doctor at Mount Carmel Hospital. He has worked there for two years.",
    question: "What is the name of Tom’s employer?",
    options: ["a hospital", "a doctor", "Mount Carmel Hospital"],
    answer: "Mount Carmel Hospital",
    topic: "Employment",
  },
  {
    id: 9,
    passage: "Tom works as a doctor at Mount Carmel Hospital. He has worked there for two years.",
    question: "What is Tom’s occupation?",
    options: ["a doctor", "two years", "Mount Carmel Hospital"],
    answer: "a doctor",
    topic: "Employment",
  },
  {
    id: 10,
    passage: "Donna has one son and one daughter. Her spouse died last year.",
    question: "How many children does Donna have?",
    options: ["1", "2", "3"],
    answer: "2",
    topic: "Family",
  },
  {
    id: 11,
    passage: "Donna has one son and one daughter. Her spouse died last year.",
    question: "What is Donna’s marital status?",
    options: ["separated", "widowed", "divorced"],
    answer: "widowed",
    topic: "Marital status",
  },
  {
    id: 12,
    passage: "Mary currently lives in Philadelphia, Pennsylvania. Prior to that, she lived for three years in Miami, Florida.",
    question: "Where does Mary live now?",
    options: ["Philadelphia", "Miami", "Los Angeles"],
    answer: "Philadelphia",
    topic: "Previous addresses",
  },
  {
    id: 13,
    passage: "Mary currently lives in Philadelphia, Pennsylvania. Prior to that, she lived for three years in Miami, Florida.",
    question: "Where did Mary live before Philadelphia?",
    options: ["New York", "Pennsylvania", "Miami"],
    answer: "Miami",
    topic: "Previous addresses",
  },
  {
    id: 14,
    passage: "Susan takes two trips each year. She visits her parents in Paris, France, for three weeks every summer. She also visits her brother in Mexico City, Mexico, for one week each December.",
    question: "How much time does Susan spend outside of the United States during these two trips each year?",
    options: ["one year", "three weeks", "four weeks"],
    answer: "four weeks",
    topic: "Travel",
  },
  {
    id: 15,
    passage: "Susan takes two trips each year. She visits her parents in Paris, France, for three weeks every summer. She also visits her brother in Mexico City, Mexico, for one week each December.",
    question: "How many trips outside of the United States does Susan take each year?",
    options: ["one trip", "two trips", "three trips"],
    answer: "two trips",
    topic: "Travel",
  },
  {
    id: 16,
    passage: "Susan takes two trips each year. She visits her parents in Paris, France, for three weeks every summer. She also visits her brother in Mexico City, Mexico, for one week each December.",
    question: "Which two countries does Susan travel to each year?",
    options: ["France and Mexico", "Canada and Mexico", "France and Japan"],
    answer: "France and Mexico",
    topic: "Travel",
  },
  {
    id: 17,
    passage: "Lisa is 5 feet 7 inches tall. She is 27 years old. She has blonde hair and green eyes.",
    question: "What is Lisa’s age?",
    options: ["5 feet 7 inches", "27", "green"],
    answer: "27",
    topic: "Personal details",
  },
  {
    id: 18,
    passage: "Lisa is 5 feet 7 inches tall. She is 27 years old. She has blonde hair and green eyes.",
    question: "What is Lisa’s height?",
    options: ["blonde", "27", "5 feet 7 inches"],
    answer: "5 feet 7 inches",
    topic: "Personal details",
  },
];

const vocab2 = [
  ["habitually", "often", "Michael is habitually late for work at the bank.", ["Michael is never late for work at the bank.", "Michael is often late for work at the bank.", "Michael was late for work at the bank yesterday."]],
  ["verify", "prove something is true", "Can you verify this information?", ["Can you prove that this information is true?", "Can you copy this information?", "Can you translate this information?"]],
  ["marital status", "married, divorced, single, or widowed", "What is your marital status?", ["When were you married to your spouse?", "Whom are you married to now?", "Are you married, divorced, single, or widowed now?"]],
  ["swear", "promise", "I swear to tell the truth.", ["I like to tell the truth.", "I promise to tell the truth.", "I forget to tell the truth."]],
  ["registered", "signed up", "John registered for an English class at the community college.", ["John finished an English class at the community college.", "John signed up for an English class at the community college.", "John taught an English class at the community college."]],
  ["spouse", "husband or wife", "Did your spouse go with you outside the United States last summer?", ["Did your husband or wife go with you last summer?", "Did your children go with you last summer?", "Did other people go with you last summer?"]],
  ["current home address", "where you live now", "What is your current home address?", ["Where do you work?", "Where were you born?", "Where do you live?"]],
  ["date of birth", "when you were born", "What is your date of birth?", ["When were you born?", "How old are you now?", "Where were you born?"]],
  ["advocated", "supported", "Mary advocated to change the working conditions at her job.", ["Mary was in charge of the working conditions at her job.", "Mary supported getting better working conditions at her job.", "Mary did not want to change the working conditions at her job."]],
  ["failed to", "did not do something", "Jim failed to send in his taxes on time.", ["Jim sent in his taxes on time.", "Jim did not send in his taxes on time.", "Jim sent in his taxes two weeks early."]],
  ["federal", "U.S. government", "Is that a federal government building?", ["Is that an important building?", "Is that a state government building?", "Is that a U.S. government building?"]],
  ["exempt", "to not have to do something", "Donna was exempt from the final exam.", ["Donna completed her final exam.", "Donna failed her final exam.", "Donna did not have to take her final exam."]],
  ["prior", "before", "Gary has prior experience teaching history.", ["Gary has taught history before.", "Gary has never taught history.", "Gary likes teaching history."]],
  ["pending", "has not been decided yet", "The decision on your loan application is pending.", ["Your loan application was approved today.", "Your loan application has not been approved yet.", "Your loan application was declined."]],
  ["Have you ever", "in your lifetime", "Have you ever visited New York?", ["In your lifetime, have you visited New York?", "Are you planning to visit New York?", "Will you visit New York next summer?"]],
  ["member", "someone who belongs to", "Scott is a member of the Parent Teacher Association.", ["Scott wants to join the Parent Teacher Association.", "Scott belongs to the Parent Teacher Association.", "Scott does not belong to the Parent Teacher Association."]],
  ["resident", "someone who lives in", "I am a resident of Texas.", ["I was born in Texas.", "I have visited Texas.", "I live in Texas now."]],
  ["requested", "asked for", "John requested information about the citizenship test.", ["John presented information about the citizenship test.", "John asked for information about the citizenship test.", "John explained information about the citizenship test."]],
  ["disability", "physical or mental impairment", "Barbara’s disability made walking difficult for her.", ["Barbara had a physical impairment that made walking difficult.", "Barbara did not like to walk very far.", "Barbara refused to walk far because she was tired."]],
  ["dependents", "someone you support financially", "Do you have any dependents?", ["Do you owe anyone money?", "Do you have a job?", "Do you support anyone financially?"]],
].map(([term, meaning, prompt, options], i) => ({ id: i + 1, term, meaning, prompt, options, answer: meaning }));

const readingVocab = {
  People: ["Abraham Lincoln", "George Washington"],
  Civics: ["American flag", "Bill of Rights", "capital", "citizen", "city", "Congress", "country", "Father of Our Country", "government", "President", "right", "Senators", "state/states", "White House"],
  Places: ["America", "United States", "U.S."],
  Holidays: ["Presidents’ Day", "Memorial Day", "Flag Day", "Independence Day", "Labor Day", "Columbus Day", "Thanksgiving"],
  "Question Words": ["How", "What", "When", "Where", "Who", "Why"],
  Verbs: ["can", "come", "do/does", "elects", "have/has", "is/are/was/be", "lives/lived", "meet", "name", "pay", "vote", "want"],
  "Function Words": ["a", "for", "here", "in", "of", "on", "the", "to", "we"],
  "Content Words": ["colors", "dollar bill", "first", "largest", "many", "most", "north", "one", "people", "second", "south"],
};

const personalTopics = [
  { key: "Name", icon: UserRound, prompts: ["What is your full legal name?", "What is your family name?", "Have you ever used another name?"] },
  { key: "Date / place of birth", icon: BookOpen, prompts: ["What is your date of birth?", "Where were you born?", "What is your country of birth?"] },
  { key: "Address", icon: Home, prompts: ["What is your current home address?", "Can you verify that address?", "Where did you live before this address?"] },
  { key: "Employment", icon: Briefcase, prompts: ["Where do you work now?", "What is your occupation?", "How long have you worked there?"] },
  { key: "Marriage / family", icon: Heart, prompts: ["What is your marital status?", "What is your spouse’s name?", "Do you have any children or dependents?"] },
  { key: "Travel", icon: Plane, prompts: ["Have you traveled outside the United States in the past five years?", "Which countries did you visit?", "How long were you outside the United States?"] },
  { key: "Organizations", icon: Users, prompts: ["Have you ever been a member of any organization, association, or club?", "Have you ever advocated for a group or cause?", "Have you ever requested an immigration benefit for someone?"] },
];

function shuffle(arr) {
  return [...arr].sort(() => Math.random() - 0.5);
}

function useQuiz(items) {
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [showResult, setShowResult] = useState(false);
  const current = items[index];
  const correctCount = Object.entries(answers).filter(([id, val]) => items.find((q) => String(q.id) === String(id))?.answer === val).length;
  const choose = (val) => {
    setAnswers((prev) => ({ ...prev, [current.id]: val }));
    setShowResult(true);
  };
  const next = () => {
    setShowResult(false);
    setIndex((i) => Math.min(i + 1, items.length - 1));
  };
  const reset = () => {
    setIndex(0);
    setAnswers({});
    setShowResult(false);
  };
  return { index, setIndex, answers, showResult, current, correctCount, choose, next, reset };
}

function QuizCard({ mode, items }) {
  const quiz = useQuiz(items);
  const q = quiz.current;
  const pct = Math.round((Object.keys(quiz.answers).length / items.length) * 100);
  const selected = quiz.answers[q.id];
  const isCorrect = selected === q.answer;
  const answerText = mode === "meaning" ? q.meaning : q.answer;
  const options = useMemo(() => mode === "meaning" ? shuffle([q.meaning, ...q.options.filter((x) => x !== q.meaning && x !== q.answer).slice(0, 2)]) : q.options, [q, mode]);

  return (
    <Card className="rounded-2xl shadow-sm border-slate-200">
      <CardContent className="p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm text-slate-500">Question {quiz.index + 1} of {items.length}</div>
            <div className="font-semibold text-slate-900">{q.topic || q.term}</div>
          </div>
          <Button variant="outline" size="sm" onClick={quiz.reset}><RotateCcw className="h-4 w-4 mr-1" />Reset</Button>
        </div>
        <Progress value={pct} />
        <div className="bg-slate-50 rounded-2xl p-4 text-slate-800 leading-relaxed">
          <div className="text-xs uppercase tracking-wide text-slate-500 mb-1">Read this</div>
          {q.passage || q.prompt}
        </div>
        <div className="text-xl font-semibold">{mode === "meaning" ? "Choose the similar meaning." : q.question}</div>
        <div className="grid gap-2">
          {options.map((opt) => {
            const picked = selected === opt;
            const right = opt === answerText;
            return (
              <button
                key={opt}
                onClick={() => quiz.choose(opt)}
                className={`text-left rounded-xl border p-3 transition ${picked ? (right ? "border-green-500 bg-green-50" : "border-red-500 bg-red-50") : "border-slate-200 hover:bg-slate-50"}`}
              >
                {opt}
              </button>
            );
          })}
        </div>
        {quiz.showResult && (
          <div className={`rounded-xl p-3 flex items-start gap-2 ${isCorrect ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"}`}>
            {isCorrect ? <CheckCircle2 className="h-5 w-5 mt-0.5" /> : <XCircle className="h-5 w-5 mt-0.5" />}
            <div>{isCorrect ? "Correct." : <>Not quite. Correct answer: <b>{answerText}</b></>}</div>
          </div>
        )}
        <div className="flex items-center justify-between">
          <div className="text-sm text-slate-500">Score: {quiz.correctCount}/{Object.keys(quiz.answers).length || 0}</div>
          <Button onClick={quiz.next} disabled={quiz.index === items.length - 1}>Next</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function FlashCards() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const allCards = Object.entries(readingVocab).flatMap(([cat, words]) => words.map((word) => ({ cat, word })));
  const filtered = allCards.filter((c) => (category === "All" || c.cat === category) && c.word.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="space-y-4">
      <div className="grid md:grid-cols-[1fr_auto] gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search reading vocabulary…" className="pl-9" />
        </div>
        <select className="border rounded-xl px-3 py-2" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option>All</option>
          {Object.keys(readingVocab).map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {filtered.map((card) => (
          <Card key={`${card.cat}-${card.word}`} className="rounded-2xl hover:shadow-md transition">
            <CardContent className="p-4 space-y-2">
              <Badge variant="secondary">{card.cat}</Badge>
              <div className="text-2xl font-bold">{card.word}</div>
              <Button variant="outline" size="sm" onClick={() => window.speechSynthesis?.speak(new SpeechSynthesisUtterance(card.word))}>
                <Volume2 className="h-4 w-4 mr-1" />Speak
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function InterviewPractice() {
  const [notes, setNotes] = useState({});
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      {personalTopics.map(({ key, icon: Icon, prompts }) => (
        <Card key={key} className="rounded-2xl">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Icon className="h-5 w-5" />
              <h3 className="font-bold text-lg">{key}</h3>
            </div>
            <div className="space-y-2">
              {prompts.map((p) => <div key={p} className="rounded-xl bg-slate-50 p-3 text-sm">Officer: {p}</div>)}
            </div>
            <textarea
              value={notes[key] || ""}
              onChange={(e) => setNotes((prev) => ({ ...prev, [key]: e.target.value }))}
              placeholder="Practice answer notes…"
              className="w-full min-h-28 border rounded-xl p-3 text-sm"
            />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function N400ModuleFirstPass() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-slate-50 text-slate-900 p-4 md:p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        <header className="space-y-2">
          <Badge>N-400 Naturalization Interview Module · First Pass</Badge>
          <h1 className="text-3xl md:text-5xl font-bold tracking-tight">Practice the words, questions, and personal topics used in the N-400 interview.</h1>
          <p className="text-slate-600 max-w-3xl">Built from USCIS practice materials: Form N-400 personal-information concepts, interview vocabulary, and naturalization reading vocabulary.</p>
        </header>

        <Tabs defaultValue="interview" className="space-y-4">
          <TabsList className="grid grid-cols-2 md:grid-cols-4 h-auto rounded-2xl">
            <TabsTrigger value="interview">Mock Interview</TabsTrigger>
            <TabsTrigger value="selftest1">Self-Test 1</TabsTrigger>
            <TabsTrigger value="vocab">Vocabulary</TabsTrigger>
            <TabsTrigger value="reading">Reading Cards</TabsTrigger>
          </TabsList>

          <TabsContent value="interview" className="space-y-4">
            <Card className="rounded-2xl bg-blue-50 border-blue-100">
              <CardContent className="p-4 text-sm text-blue-900">Goal: help the applicant answer personal N-400 questions out loud. Keep answers short, truthful, and consistent with the actual N-400.</CardContent>
            </Card>
            <InterviewPractice />
          </TabsContent>

          <TabsContent value="selftest1">
            <QuizCard mode="reading" items={selfTest1} />
          </TabsContent>

          <TabsContent value="vocab">
            <QuizCard mode="meaning" items={vocab2} />
          </TabsContent>

          <TabsContent value="reading">
            <FlashCards />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
