import { useState, useEffect } from "react";
import axios from "axios";
import { useAuth } from "../hooks/useAuth";
import { apiBaseURL } from "../constants";
import AddRecommendedFoodDialog from "../components/AddRecommendedFoodDialog";
import { useNavigate } from "react-router-dom";
import MainContentLayout from "../components/MainContentLayout";
import { BiPlus } from "react-icons/bi";

export default function Dashboard() {
    const navigate = useNavigate();
    const { user, setUser } = useAuth();
    const [recommendations, setRecommendations] = useState([]);
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [selectedRec, setSelectedRec] = useState(null);

    function logRecommendation(food, amount) {
        const newFood = {
            id: `${food.fdc_id}-${new Date().toISOString()}`,
            date: new Date(),
            food: food,
            amount: amount,
        };
        setUser({ ...user, loggedFood: [...user.loggedFood, newFood] });
        navigate("/track");
    }

    useEffect(() => {
        axios({
            method: "POST",
            url: apiBaseURL + "/api/recommend",
            data: {
                age: user.age,
                sex: user.sex,
                isPregnant: user.isPregnant,
                isLactating: user.isLactating,
                macroRatio: user.macroRatio,
                heightInches: user.height,
                weightPounds: user.weight,
                foodLog: user.loggedFood
                    .filter((food) => {
                        const foodDate = new Date(food.date);
                        const currentDate = new Date();
                        return (
                            foodDate.getFullYear() ===
                                currentDate.getFullYear() &&
                            foodDate.getMonth() === currentDate.getMonth() &&
                            foodDate.getDate() === currentDate.getDate()
                        );
                    })
                    .map((food) => {
                        return {
                            fdc_id: food.food.fdc_id,
                            amount: food.amount ? parseFloat(food.amount) : 0,
                        };
                    }),
            },
        })
            .then((response) => {
                const recs = response.data;
                console.log(recs)
                setRecommendations(recs);
            })
            .catch((error) => {
                if (error) {
                    console.log(error);
                }
            });
    }, [user]);

    return (
        <MainContentLayout
            tabTitle="Sabrosa Health"
            headerTitle={`Welcome, ${user ? user.firstName : ""}!`}
            headerSubtitle="Here are your recommendations for today"
        >
            <div className="p-4">
                <div className="p-2 mx-auto w-full flex flex-col items-center rounded-lg bg-gray-100 shadow-md min-h-0">
                    {selectedRec && (
                        <AddRecommendedFoodDialog
                            isOpen={isDialogOpen}
                            setIsOpen={setIsDialogOpen}
                            recommendedFood={selectedRec}
                            addCallback={logRecommendation}
                        />
                    )}
                    <div className="w-full grid grid-cols-2 gap-4">
                        {recommendations.map((rec, i) => {
                            return (
                              <div className="flex flex-col border-b border-gray-200 rounded-lg last:border-b-0">
                                <div
                                    key={i}
                                    className="flex p-2 justify-between items-center"
                                >
                                    <p className="font-semibold text-xl hover:text-cyan-600 border-b border-gray-500 hover:cursor-pointer"
                                    onClick={() => {
                                      setSelectedRec(rec);
                                      setIsDialogOpen(true);
                                  }}> 
                                        {`${
                                            rec.shortened_name
                                                ? rec.shortened_name
                                                : rec.name
                                        } ${rec.emojis ? rec.emojis : ""}`}
                                    </p>
                                    {/* <span className="animate-spin opacity-20 absolute" style={{fontSize: "48px"}}>{rec.emojis}</span> */}
                                    <div className="flex items-center hover:text-cyan-600 rounded-full">
                                        <button
                                            className="m-1 p-1 text-center text-2xl"
                                            onClick={() => {
                                                setSelectedRec(rec);
                                                setIsDialogOpen(true);
                                            }}
                                        >
                                            <BiPlus />
                                        </button>
                                    </div>
                                </div>
                                <div className="p-2">A significant source of:<div className="px-2">{rec.significant_1}<br/>{rec.significant_2}<br/>{rec.significant_3}</div></div>
                              </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        </MainContentLayout>
    );
}
